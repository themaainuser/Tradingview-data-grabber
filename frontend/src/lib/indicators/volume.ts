import { int, num, output, periodParam, typicalPrice, VALUE, windowParam } from './helpers';
import {
	clamp,
	closeLocationValue,
	diff,
	div,
	emaSpan,
	mul,
	nanArray,
	pctDiff,
	rateOfChange,
	rollingMean,
	rollingStd,
	rollingSum,
	sub,
	zScore,
	zip
} from './math';
import type { Series } from './math';
import type { IndicatorDefinition, OhlcvColumns } from './types';

const nz = Number.isFinite;

/** Cumulative sum of `clv * volume`; bars with non-finite inputs are skipped (NaN output). */
function accumulationDistribution(d: OhlcvColumns): Series {
	const n = d.close.length;
	const clv = closeLocationValue(d.high, d.low, d.close);
	const out = nanArray(n);
	let acc = 0;
	for (let i = 0; i < n; i++) {
		const flow = clv[i] * d.volume[i];
		if (!nz(flow)) continue;
		acc += flow;
		out[i] = acc;
	}
	return out;
}

/** Klinger volume oscillator; state restarts after a non-finite bar. */
function klinger(d: OhlcvColumns, fast: number, slow: number, signal: number): [Series, Series] {
	const n = d.close.length;
	const force = nanArray(n);
	let started = false;
	let prevHlc = 0;
	let prevRange = 0;
	let prevTrend = 0;
	let cm = 0;
	for (let i = 0; i < n; i++) {
		const h = d.high[i];
		const l = d.low[i];
		const c = d.close[i];
		const v = d.volume[i];
		if (!(nz(h) && nz(l) && nz(c) && nz(v))) {
			started = false;
			continue;
		}
		const hlc = h + l + c;
		const range = h - l;
		if (!started) {
			started = true;
			prevHlc = hlc;
			prevRange = range;
			prevTrend = 0;
			continue;
		}
		const trend = hlc > prevHlc ? 1 : -1;
		cm = trend === prevTrend ? cm + range : prevRange + range;
		force[i] = cm === 0 ? 0 : v * Math.abs(2 * (range / cm - 1)) * trend * 100;
		prevHlc = hlc;
		prevRange = range;
		prevTrend = trend;
	}
	const kvo = sub(emaSpan(force, fast), emaSpan(force, slow));
	return [kvo, emaSpan(kvo, signal)];
}

/** Negative (volume falls) or Positive (volume rises) Volume Index, starting at `start`. */
function volumeIndex(d: OhlcvColumns, start: number, onFallingVolume: boolean): Series {
	const n = d.close.length;
	const out = nanArray(n);
	let value = start;
	let prevClose = NaN;
	let prevVolume = NaN;
	for (let i = 0; i < n; i++) {
		const c = d.close[i];
		const v = d.volume[i];
		if (!nz(c) || !nz(v)) continue;
		if (nz(prevClose) && prevClose !== 0) {
			const triggered = onFallingVolume ? v < prevVolume : v > prevVolume;
			if (triggered) value *= c / prevClose;
		}
		out[i] = value;
		prevClose = c;
		prevVolume = v;
	}
	return out;
}

export const volumeIndicators: IndicatorDefinition[] = [
	{
		id: 'obv',
		name: 'On-Balance Volume',
		short: 'OBV',
		description:
			'Running total of volume, added on up closes and subtracted on down closes (starts at 0).',
		category: 'Volume',
		pane: 'separate',
		params: [],
		outputs: VALUE,
		compute: (d) => {
			const n = d.close.length;
			const out = nanArray(n);
			let acc = 0;
			let prevClose = NaN;
			for (let i = 0; i < n; i++) {
				const c = d.close[i];
				const v = d.volume[i];
				if (!nz(c) || !nz(v)) continue;
				if (nz(prevClose)) acc += c > prevClose ? v : c < prevClose ? -v : 0;
				prevClose = c;
				out[i] = acc;
			}
			return [out];
		}
	},
	{
		id: 'ad_line',
		name: 'Accumulation/Distribution Line',
		short: 'A/D',
		description:
			'Running total of close-location value times volume; tracks buying versus selling pressure.',
		category: 'Volume',
		pane: 'separate',
		params: [],
		outputs: VALUE,
		compute: (d) => [accumulationDistribution(d)]
	},
	{
		id: 'cmf',
		name: 'Chaikin Money Flow',
		short: 'CMF',
		description:
			'Volume-weighted close-location value over N bars, from -1 (selling) to +1 (buying).',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => {
			const flow = mul(closeLocationValue(d.high, d.low, d.close), d.volume);
			return [clamp(div(rollingSum(flow, p.period), rollingSum(d.volume, p.period)), -1, 1)];
		}
	},
	{
		id: 'chaikin_osc',
		name: 'Chaikin Oscillator',
		short: 'ChOsc',
		description: 'Difference between fast and slow EMAs of the Accumulation/Distribution line.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [int('fast', 'Fast span', 3, 1, 100), int('slow', 'Slow span', 10, 2, 300)],
		outputs: VALUE,
		compute: (d, p) => {
			const ad = accumulationDistribution(d);
			return [sub(emaSpan(ad, p.fast), emaSpan(ad, p.slow))];
		}
	},
	{
		id: 'mfi',
		name: 'Money Flow Index',
		short: 'MFI',
		description:
			'Volume-weighted RSI: share of positive typical-price money flow over N bars, 0-100.',
		category: 'Volume',
		pane: 'separate',
		guides: [20, 80],
		params: [periodParam(14, 2)],
		outputs: VALUE,
		compute: (d, p) => {
			const n = d.close.length;
			const tp = typicalPrice(d);
			const positive = nanArray(n);
			const negative = nanArray(n);
			for (let i = 1; i < n; i++) {
				const flow = tp[i] * d.volume[i];
				const change = tp[i] - tp[i - 1];
				positive[i] = change > 0 ? flow : change <= 0 ? 0 : NaN;
				negative[i] = change < 0 ? flow : change >= 0 ? 0 : NaN;
			}
			return [
				zip(rollingSum(positive, p.period), rollingSum(negative, p.period), (up, down) => {
					const pos = Math.max(0, up);
					const neg = Math.max(0, down);
					if (neg === 0) return pos > 0 ? 100 : Number.isNaN(up + down) ? NaN : 50;
					return 100 - 100 / (1 + pos / neg);
				})
			];
		}
	},
	{
		id: 'force_index',
		name: 'Force Index',
		short: 'FI',
		description:
			'EMA of volume times the bar-to-bar close change; measures the power behind moves.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [periodParam(13)],
		outputs: VALUE,
		compute: (d, p) => [emaSpan(mul(d.volume, diff(d.close, 1)), p.period)]
	},
	{
		id: 'ease_of_movement',
		name: 'Ease of Movement',
		short: 'EMV',
		description:
			'SMA of midpoint movement scaled by the volume-to-range ratio; price move per unit of volume.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [periodParam(14), num('scale', 'Volume scale', 1_000_000, 1, 1e12, 1)],
		outputs: VALUE,
		compute: (d, p) => {
			const n = d.close.length;
			const raw = nanArray(n);
			for (let i = 1; i < n; i++) {
				const move = (d.high[i] + d.low[i]) / 2 - (d.high[i - 1] + d.low[i - 1]) / 2;
				const range = d.high[i] - d.low[i];
				raw[i] = d.volume[i] > 0 ? (move * range * p.scale) / d.volume[i] : NaN;
			}
			return [rollingMean(raw, p.period)];
		}
	},
	{
		id: 'volume_sma',
		name: 'Volume SMA',
		short: 'Vol SMA',
		description: 'Simple moving average of bar volume.',
		category: 'Volume',
		pane: 'separate',
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [rollingMean(d.volume, p.period)]
	},
	{
		id: 'volume_roc',
		name: 'Volume Rate of Change',
		short: 'Vol ROC',
		description: 'Percent change of bar volume over the last N bars.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => [rateOfChange(d.volume, p.period)]
	},
	{
		id: 'relative_volume',
		name: 'Relative Volume',
		short: 'RVOL',
		description: 'Bar volume divided by its N-bar average volume (1 = normal activity).',
		category: 'Volume',
		pane: 'separate',
		guides: [1],
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [div(d.volume, rollingMean(d.volume, p.period))]
	},
	{
		id: 'volume_zscore',
		name: 'Volume Z-Score',
		short: 'Vol z',
		description:
			'Standard score of bar volume against its N-bar mean using the sample standard deviation.',
		category: 'Volume',
		pane: 'separate',
		guides: [-2, 0, 2],
		params: [windowParam(20)],
		outputs: VALUE,
		compute: (d, p) => {
			const mean = rollingMean(d.volume, p.window);
			const sd = rollingStd(d.volume, p.window, 1);
			return [zScore(d.volume, mean, sd)];
		}
	},
	{
		id: 'volume_oscillator',
		name: 'Volume Oscillator',
		short: 'VO',
		description: 'Percent gap between fast and slow EMAs of volume.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [int('fast', 'Fast span', 5, 1, 100), int('slow', 'Slow span', 10, 2, 300)],
		outputs: VALUE,
		compute: (d, p) => {
			const slow = emaSpan(d.volume, p.slow);
			return [pctDiff(emaSpan(d.volume, p.fast), slow)];
		}
	},
	{
		id: 'klinger',
		name: 'Klinger Volume Oscillator',
		short: 'KVO',
		description:
			'Difference of fast and slow EMAs of trend-signed volume force, with an EMA signal line.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [
			int('fast', 'Fast span', 34, 1, 200),
			int('slow', 'Slow span', 55, 2, 400),
			int('signal', 'Signal span', 13, 1, 100)
		],
		outputs: [output('kvo', 'KVO'), output('signal', 'Signal')],
		compute: (d, p) => klinger(d, p.fast, p.slow, p.signal)
	},
	{
		id: 'pvt',
		name: 'Price Volume Trend',
		short: 'PVT',
		description: 'Running total of volume times the percent close change.',
		category: 'Volume',
		pane: 'separate',
		params: [],
		outputs: VALUE,
		compute: (d) => {
			const n = d.close.length;
			const out = nanArray(n);
			let acc = 0;
			let prevClose = NaN;
			for (let i = 0; i < n; i++) {
				const c = d.close[i];
				const v = d.volume[i];
				if (!nz(c) || !nz(v)) continue;
				if (nz(prevClose) && prevClose !== 0) acc += v * (c / prevClose - 1);
				prevClose = c;
				out[i] = acc;
			}
			return [out];
		}
	},
	{
		id: 'nvi',
		name: 'Negative Volume Index',
		short: 'NVI',
		description:
			'Index that only follows the close on bars where volume fell versus the prior bar.',
		category: 'Volume',
		pane: 'separate',
		params: [num('start', 'Start value', 1000, 1, 1e6, 1)],
		outputs: VALUE,
		compute: (d, p) => [volumeIndex(d, p.start, true)]
	},
	{
		id: 'pvi',
		name: 'Positive Volume Index',
		short: 'PVI',
		description:
			'Index that only follows the close on bars where volume rose versus the prior bar.',
		category: 'Volume',
		pane: 'separate',
		params: [num('start', 'Start value', 1000, 1, 1e6, 1)],
		outputs: VALUE,
		compute: (d, p) => [volumeIndex(d, p.start, false)]
	},
	{
		id: 'vwap_distance',
		name: 'Rolling VWAP Distance %',
		short: 'VWAP dist',
		description:
			'Percent distance of the close from the N-bar rolling volume-weighted average price.',
		category: 'Volume',
		pane: 'separate',
		guides: [0],
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => {
			const vwap = div(
				rollingSum(mul(typicalPrice(d), d.volume), p.period),
				rollingSum(d.volume, p.period)
			);
			return [pctDiff(d.close, vwap)];
		}
	},
	{
		id: 'dollar_volume',
		name: 'Dollar Volume',
		short: '$ Vol',
		description: 'Traded value per bar: close times volume.',
		category: 'Volume',
		pane: 'separate',
		params: [],
		outputs: VALUE,
		compute: (d) => [mul(d.close, d.volume)]
	}
];
