import { int, medianPrice, output, periodParam, typicalPrice, VALUE } from './helpers';
import {
	abs,
	add,
	clamp,
	diff,
	div,
	emaSpan,
	finiteRun,
	isDegenerate,
	map,
	nanArray,
	offset,
	pctDiff,
	rateOfChange,
	rollingMax,
	rollingMean,
	rollingMin,
	rollingPercentRank,
	rollingRegression,
	rollingSum,
	rsi,
	rsiFromChanges,
	scale,
	shift,
	stochasticPosition,
	sub,
	swma4,
	wma,
	zip
} from './math';
import type { Series } from './math';
import type { IndicatorDefinition } from './types';

/** Commodity Channel Index: (tp - SMA) / (0.015 * mean absolute deviation). */
function cci(tp: Series, period: number): Series {
	const n = tp.length;
	const out = nanArray(n);
	const run = finiteRun(tp);
	for (let i = period - 1; i < n; i++) {
		if (run[i] < period) continue;
		let mean = 0;
		for (let j = i - period + 1; j <= i; j++) mean += tp[j];
		mean /= period;
		let dev = 0;
		for (let j = i - period + 1; j <= i; j++) dev += Math.abs(tp[j] - mean);
		dev /= period;
		if (!isDegenerate(dev, mean)) out[i] = (tp[i] - mean) / (0.015 * dev);
	}
	return out;
}

/** Ehlers Fisher Transform of the midpoint's position in its N-bar range; signal = previous value. */
function fisher(mid: Series, period: number): [Series, Series] {
	const n = mid.length;
	const fish = nanArray(n);
	const signal = nanArray(n);
	const hi = rollingMax(mid, period);
	const lo = rollingMin(mid, period);
	let started = false;
	let x = 0;
	let f = 0;
	for (let i = 0; i < n; i++) {
		if (!(Number.isFinite(hi[i]) && Number.isFinite(lo[i]))) {
			started = false;
			continue;
		}
		const range = hi[i] - lo[i];
		if (range === 0) continue;
		if (!started) {
			x = 0;
			f = 0;
		}
		const nextX = Math.min(
			0.999,
			Math.max(-0.999, 0.66 * ((mid[i] - lo[i]) / range - 0.5) + 0.67 * x)
		);
		const nextF = 0.5 * Math.log((1 + nextX) / (1 - nextX)) + 0.5 * f;
		fish[i] = nextF;
		if (started) signal[i] = f;
		started = true;
		x = nextX;
		f = nextF;
	}
	return [fish, signal];
}

/** Signed count of consecutive up (+) or down (-) closes; unchanged closes reset to 0. */
function streaks(close: Series): Series {
	const n = close.length;
	const out = nanArray(n);
	let prev = 0;
	for (let i = 0; i < n; i++) {
		const c = close[i];
		if (!Number.isFinite(c)) {
			prev = 0;
			continue;
		}
		if (i === 0 || !Number.isFinite(close[i - 1])) {
			prev = 0;
		} else if (c > close[i - 1]) {
			prev = prev > 0 ? prev + 1 : 1;
		} else if (c < close[i - 1]) {
			prev = prev < 0 ? prev - 1 : -1;
		} else {
			prev = 0;
		}
		out[i] = prev;
	}
	return out;
}

export const momentumIndicators: IndicatorDefinition[] = [
	{
		id: 'rsi',
		name: 'Relative Strength Index',
		short: 'RSI',
		description:
			'Ratio of Wilder-smoothed average gains to average losses, scaled 0-100 (backend-compatible).',
		category: 'Momentum',
		pane: 'separate',
		guides: [30, 70],
		params: [periodParam(14, 2)],
		outputs: [output('value', 'RSI')],
		compute: (d, p) => [rsi(d.close, p.period)]
	},
	{
		id: 'stochastic',
		name: 'Stochastic Oscillator',
		short: 'Stoch',
		description:
			'Position of the close within the N-bar high-low range (%K, smoothed) and its average (%D).',
		category: 'Momentum',
		pane: 'separate',
		guides: [20, 80],
		params: [
			periodParam(14, 1),
			int('kSmooth', '%K smoothing', 3, 1, 100),
			int('dPeriod', '%D period', 3, 1, 100)
		],
		outputs: [output('k', '%K'), output('d', '%D')],
		compute: (d, p) => {
			const raw = stochasticPosition(
				d.close,
				rollingMax(d.high, p.period),
				rollingMin(d.low, p.period)
			);
			const k = clamp(rollingMean(raw, p.kSmooth), 0, 100);
			return [k, clamp(rollingMean(k, p.dPeriod), 0, 100)];
		}
	},
	{
		id: 'stoch_rsi',
		name: 'Stochastic RSI',
		short: 'StochRSI',
		description:
			'Stochastic oscillator applied to RSI: where RSI sits within its own recent range (0-100).',
		category: 'Momentum',
		pane: 'separate',
		guides: [20, 80],
		params: [
			int('rsiPeriod', 'RSI period', 14, 2, 200),
			int('stochPeriod', 'Stochastic period', 14, 2, 200),
			int('kSmooth', '%K smoothing', 3, 1, 100),
			int('dPeriod', '%D period', 3, 1, 100)
		],
		outputs: [output('k', '%K'), output('d', '%D')],
		compute: (d, p) => {
			const r = rsi(d.close, p.rsiPeriod);
			const raw = stochasticPosition(r, rollingMax(r, p.stochPeriod), rollingMin(r, p.stochPeriod));
			const k = clamp(rollingMean(raw, p.kSmooth), 0, 100);
			return [k, clamp(rollingMean(k, p.dPeriod), 0, 100)];
		}
	},
	{
		id: 'macd',
		name: 'MACD',
		short: 'MACD',
		description:
			'Difference of fast and slow EMAs of close, its EMA signal line and the histogram between them.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [
			int('fast', 'Fast span', 12, 1, 200),
			int('slow', 'Slow span', 26, 2, 500),
			int('signal', 'Signal span', 9, 1, 200)
		],
		outputs: [output('macd', 'MACD'), output('signal', 'Signal'), output('hist', 'Histogram')],
		compute: (d, p) => {
			const macd = sub(emaSpan(d.close, p.fast), emaSpan(d.close, p.slow));
			const signal = emaSpan(macd, p.signal);
			return [macd, signal, sub(macd, signal)];
		}
	},
	{
		id: 'roc',
		name: 'Rate of Change',
		short: 'ROC',
		description: 'Percent change of the close over the last N bars.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(12)],
		outputs: VALUE,
		compute: (d, p) => [rateOfChange(d.close, p.period)]
	},
	{
		id: 'momentum',
		name: 'Momentum',
		short: 'MOM',
		description: 'Absolute price change of the close over the last N bars.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(10)],
		outputs: VALUE,
		compute: (d, p) => [diff(d.close, p.period)]
	},
	{
		id: 'cci',
		name: 'Commodity Channel Index',
		short: 'CCI',
		description:
			'Deviation of the typical price from its SMA in units of 0.015 mean absolute deviations.',
		category: 'Momentum',
		pane: 'separate',
		guides: [-100, 100],
		params: [periodParam(20, 2, 300)],
		outputs: VALUE,
		compute: (d, p) => [cci(typicalPrice(d), p.period)]
	},
	{
		id: 'williams_r',
		name: 'Williams %R',
		short: '%R',
		description:
			'Distance of the close below the N-bar high as a percent of the range, from -100 to 0.',
		category: 'Momentum',
		pane: 'separate',
		guides: [-80, -20],
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => {
			const position = stochasticPosition(
				d.close,
				rollingMax(d.high, p.period),
				rollingMin(d.low, p.period)
			);
			return [clamp(offset(position, -100), -100, 0)];
		}
	},
	{
		id: 'tsi',
		name: 'True Strength Index',
		short: 'TSI',
		description:
			'Double-EMA-smoothed price momentum divided by double-smoothed absolute momentum (x100).',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [int('long', 'Long span', 25, 2, 300), int('short', 'Short span', 13, 1, 200)],
		outputs: VALUE,
		compute: (d, p) => {
			const m = diff(d.close, 1);
			const numerator = emaSpan(emaSpan(m, p.long), p.short);
			const den = emaSpan(emaSpan(abs(m), p.long), p.short);
			return [div(scale(numerator, 100), den)];
		}
	},
	{
		id: 'ultimate_oscillator',
		name: 'Ultimate Oscillator',
		short: 'UO',
		description: 'Weighted blend of buying pressure over three horizons, scaled 0-100.',
		category: 'Momentum',
		pane: 'separate',
		guides: [30, 70],
		params: [
			int('short', 'Short period', 7, 1, 100),
			int('mid', 'Middle period', 14, 1, 200),
			int('long', 'Long period', 28, 1, 400)
		],
		outputs: VALUE,
		compute: (d, p) => {
			const n = d.close.length;
			const bp = nanArray(n);
			const tr = nanArray(n);
			for (let i = 1; i < n; i++) {
				const lo = Math.min(d.low[i], d.close[i - 1]);
				bp[i] = d.close[i] - lo;
				tr[i] = Math.max(d.high[i], d.close[i - 1]) - lo;
			}
			const avg = (w: number) => div(rollingSum(bp, w), rollingSum(tr, w));
			const a1 = avg(p.short);
			const a2 = avg(p.mid);
			const a3 = avg(p.long);
			const out = nanArray(n);
			for (let i = 0; i < n; i++) out[i] = (100 * (4 * a1[i] + 2 * a2[i] + a3[i])) / 7;
			return [clamp(out, 0, 100)];
		}
	},
	{
		id: 'awesome_oscillator',
		name: 'Awesome Oscillator',
		short: 'AO',
		description: 'Difference between fast and slow SMAs of the bar midpoint (high + low) / 2.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [int('fast', 'Fast period', 5, 1, 200), int('slow', 'Slow period', 34, 2, 500)],
		outputs: VALUE,
		compute: (d, p) => {
			const mid = medianPrice(d);
			return [sub(rollingMean(mid, p.fast), rollingMean(mid, p.slow))];
		}
	},
	{
		id: 'accelerator_oscillator',
		name: 'Accelerator Oscillator',
		short: 'AC',
		description: 'Awesome Oscillator minus its own SMA; shows acceleration of momentum.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [
			int('fast', 'Fast period', 5, 1, 200),
			int('slow', 'Slow period', 34, 2, 500),
			int('smooth', 'Smoothing period', 5, 1, 200)
		],
		outputs: VALUE,
		compute: (d, p) => {
			const mid = medianPrice(d);
			const ao = sub(rollingMean(mid, p.fast), rollingMean(mid, p.slow));
			return [sub(ao, rollingMean(ao, p.smooth))];
		}
	},
	{
		id: 'cmo',
		name: 'Chande Momentum Oscillator',
		short: 'CMO',
		description:
			'Net sum of up and down closes over N bars as a percent of total movement (-100 to 100).',
		category: 'Momentum',
		pane: 'separate',
		guides: [-50, 50],
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => {
			const change = diff(d.close, 1);
			const up = rollingSum(
				map(change, (x) => (x > 0 ? x : x <= 0 ? 0 : NaN)),
				p.period
			);
			const down = rollingSum(
				map(change, (x) => (x < 0 ? -x : x >= 0 ? 0 : NaN)),
				p.period
			);
			return [
				zip(up, down, (u, dn) => {
					const total = Math.max(0, u) + Math.max(0, dn);
					return total === 0 ? 0 : (100 * (Math.max(0, u) - Math.max(0, dn))) / total;
				})
			];
		}
	},
	{
		id: 'trix',
		name: 'TRIX',
		short: 'TRIX',
		description: 'One-bar percent change of a triple-smoothed EMA of close.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(15)],
		outputs: VALUE,
		compute: (d, p) => {
			const e3 = emaSpan(emaSpan(emaSpan(d.close, p.period), p.period), p.period);
			return [pctDiff(e3, shift(e3, 1))];
		}
	},
	{
		id: 'ppo',
		name: 'Percentage Price Oscillator',
		short: 'PPO',
		description: 'MACD expressed as a percent of the slow EMA, with signal line and histogram.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [
			int('fast', 'Fast span', 12, 1, 200),
			int('slow', 'Slow span', 26, 2, 500),
			int('signal', 'Signal span', 9, 1, 200)
		],
		outputs: [output('ppo', 'PPO'), output('signal', 'Signal'), output('hist', 'Histogram')],
		compute: (d, p) => {
			const slow = emaSpan(d.close, p.slow);
			const ppo = scale(div(sub(emaSpan(d.close, p.fast), slow), slow), 100);
			const signal = emaSpan(ppo, p.signal);
			return [ppo, signal, sub(ppo, signal)];
		}
	},
	{
		id: 'apo',
		name: 'Absolute Price Oscillator',
		short: 'APO',
		description: 'Difference between fast and slow EMAs of close in price units.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [int('fast', 'Fast span', 12, 1, 200), int('slow', 'Slow span', 26, 2, 500)],
		outputs: VALUE,
		compute: (d, p) => [sub(emaSpan(d.close, p.fast), emaSpan(d.close, p.slow))]
	},
	{
		id: 'dpo',
		name: 'Detrended Price Oscillator',
		short: 'DPO',
		description:
			'Close from N/2 + 1 bars ago minus the current N-bar SMA; strips the trend to expose cycles.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [
			sub(shift(d.close, Math.floor(p.period / 2) + 1), rollingMean(d.close, p.period))
		]
	},
	{
		id: 'fisher',
		name: 'Fisher Transform',
		short: 'Fisher',
		description:
			'Gaussianising transform of the midpoint position within its N-bar range, plus a one-bar-lag signal.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(10, 2)],
		outputs: [output('fisher', 'Fisher'), output('signal', 'Signal')],
		compute: (d, p) => fisher(medianPrice(d), p.period)
	},
	{
		id: 'connors_rsi',
		name: 'Connors RSI',
		short: 'CRSI',
		description:
			'Average of price RSI, up/down streak RSI and the percent rank of the one-bar return.',
		category: 'Momentum',
		pane: 'separate',
		guides: [20, 80],
		params: [
			int('rsiPeriod', 'RSI period', 3, 2, 100),
			int('streakPeriod', 'Streak RSI period', 2, 2, 100),
			int('rankPeriod', 'Percent-rank window', 100, 2, 200)
		],
		outputs: [
			output('crsi', 'Connors RSI'),
			output('rsi', 'Price RSI'),
			output('streak_rsi', 'Streak RSI'),
			output('percent_rank', 'Percent rank')
		],
		compute: (d, p) => {
			const price = rsi(d.close, p.rsiPeriod);
			const streak = rsi(streaks(d.close), p.streakPeriod);
			const rank = rollingPercentRank(rateOfChange(d.close, 1), p.rankPeriod);
			const n = d.close.length;
			const crsi = nanArray(n);
			for (let i = 0; i < n; i++) crsi[i] = (price[i] + streak[i] + rank[i]) / 3;
			return [crsi, price, streak, rank];
		}
	},
	{
		id: 'kst',
		name: 'Know Sure Thing',
		short: 'KST',
		description:
			'Weighted sum of four smoothed rates of change across short to long horizons, with a signal SMA.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [
			int('roc1', 'ROC 1', 10, 1, 300),
			int('roc2', 'ROC 2', 15, 1, 300),
			int('roc3', 'ROC 3', 20, 1, 300),
			int('roc4', 'ROC 4', 30, 1, 300),
			int('sma1', 'SMA 1', 10, 1, 200),
			int('sma2', 'SMA 2', 10, 1, 200),
			int('sma3', 'SMA 3', 10, 1, 200),
			int('sma4', 'SMA 4', 15, 1, 200),
			int('signal', 'Signal period', 9, 1, 200)
		],
		outputs: [output('kst', 'KST'), output('signal', 'Signal')],
		compute: (d, p) => {
			const term = (roc: number, sma: number, weight: number) =>
				scale(rollingMean(rateOfChange(d.close, roc), sma), weight);
			const kst = add(
				add(term(p.roc1, p.sma1, 1), term(p.roc2, p.sma2, 2)),
				add(term(p.roc3, p.sma3, 3), term(p.roc4, p.sma4, 4))
			);
			return [kst, rollingMean(kst, p.signal)];
		}
	},
	{
		id: 'coppock',
		name: 'Coppock Curve',
		short: 'Coppock',
		description: 'WMA of the sum of a long and a short rate of change of close.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [
			int('longRoc', 'Long ROC', 14, 1, 300),
			int('shortRoc', 'Short ROC', 11, 1, 300),
			int('wmaPeriod', 'WMA period', 10, 1, 200)
		],
		outputs: VALUE,
		compute: (d, p) => [
			wma(add(rateOfChange(d.close, p.longRoc), rateOfChange(d.close, p.shortRoc)), p.wmaPeriod)
		]
	},
	{
		id: 'rvi',
		name: 'Relative Vigor Index',
		short: 'RVI',
		description:
			'Ratio of smoothed close-open to smoothed high-low; closes tend to exceed opens in uptrends.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(10)],
		outputs: [output('rvi', 'RVI'), output('signal', 'Signal')],
		compute: (d, p) => {
			const numer = swma4(sub(d.close, d.open));
			const denom = swma4(sub(d.high, d.low));
			const rvi = div(rollingMean(numer, p.period), rollingMean(denom, p.period));
			return [rvi, swma4(rvi)];
		}
	},
	{
		id: 'bop',
		name: 'Balance of Power',
		short: 'BOP',
		description:
			'SMA of (close - open) / (high - low): who controls each bar, buyers (+1) or sellers (-1).',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(14)],
		outputs: VALUE,
		compute: (d, p) => {
			const raw = zip(sub(d.close, d.open), sub(d.high, d.low), (body, range) =>
				range === 0 ? 0 : body / range
			);
			return [rollingMean(raw, p.period)];
		}
	},
	{
		id: 'elder_ray',
		name: 'Elder Ray',
		short: 'Elder',
		description:
			'Bull power (high - EMA) and bear power (low - EMA) relative to an N-span EMA of close.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(13)],
		outputs: [output('bull', 'Bull power'), output('bear', 'Bear power')],
		compute: (d, p) => {
			const e = emaSpan(d.close, p.period);
			return [sub(d.high, e), sub(d.low, e)];
		}
	},
	{
		id: 'cfo',
		name: 'Chande Forecast Oscillator',
		short: 'CFO',
		description: 'Percent gap between the close and its N-bar linear-regression value.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(14, 2)],
		outputs: VALUE,
		compute: (d, p) => [
			zip(d.close, rollingRegression(d.close, p.period).value, (c, f) =>
				c === 0 ? NaN : (100 * (c - f)) / c
			)
		]
	},
	{
		id: 'qstick',
		name: 'QStick',
		short: 'QStick',
		description:
			'SMA of close minus open; positive when buyers close bars above the open on average.',
		category: 'Momentum',
		pane: 'separate',
		guides: [0],
		params: [periodParam(8)],
		outputs: VALUE,
		compute: (d, p) => [rollingMean(sub(d.close, d.open), p.period)]
	},
	{
		id: 'rmi',
		name: 'Relative Momentum Index',
		short: 'RMI',
		description:
			'RSI variant that measures changes over a K-bar lookback instead of one bar (0-100).',
		category: 'Momentum',
		pane: 'separate',
		guides: [30, 70],
		params: [periodParam(14, 2), int('lookback', 'Momentum lookback', 5, 1, 100)],
		outputs: VALUE,
		compute: (d, p) => [rsiFromChanges(diff(d.close, p.lookback), p.period)]
	}
];
