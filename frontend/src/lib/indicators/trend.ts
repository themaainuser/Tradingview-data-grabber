import {
	int,
	medianPrice,
	multParam,
	num,
	output,
	periodParam,
	typicalPrice,
	VALUE
} from './helpers';
import {
	abs,
	add,
	atrWilder,
	diff,
	div,
	emaSpan,
	isDegenerate,
	mul,
	nanArray,
	pctDiff,
	rollingArgMax,
	rollingArgMin,
	rollingMax,
	rollingMean,
	rollingMin,
	rollingRegression,
	rollingStd,
	rollingSum,
	scale,
	shift,
	sub,
	trueRange,
	wilder,
	wma,
	zip
} from './math';
import type { Series } from './math';
import type { IndicatorDefinition } from './types';

const nz = Number.isFinite;

/** Kaufman's adaptive MA; the first value appears at bar `period` and is seeded from the prior close. */
function kama(close: Series, period: number, fast: number, slow: number): Series {
	const n = close.length;
	const out = nanArray(n);
	const change = abs(diff(close, period));
	const path = rollingSum(abs(diff(close, 1)), period);
	const fastSc = 2 / (fast + 1);
	const slowSc = 2 / (slow + 1);
	let prev = NaN;
	for (let i = 0; i < n; i++) {
		if (!nz(close[i]) || !(path[i] >= 0) || !nz(change[i])) continue;
		if (!nz(prev)) prev = i > 0 && nz(close[i - 1]) ? close[i - 1] : close[i];
		const er = path[i] > 0 ? change[i] / path[i] : 0;
		const sc = (er * (fastSc - slowSc) + slowSc) ** 2;
		prev += sc * (close[i] - prev);
		out[i] = prev;
	}
	return out;
}

/** Wilder's Parabolic SAR. State restarts after any non-finite bar. */
function parabolicSar(
	high: Series,
	low: Series,
	close: Series,
	step: number,
	maxStep: number
): Series {
	const n = high.length;
	const out = nanArray(n);
	let run = 0;
	let long = true;
	let sar = 0;
	let ep = 0;
	let af = step;
	for (let i = 0; i < n; i++) {
		const h = high[i];
		const l = low[i];
		if (!(nz(h) && nz(l) && nz(close[i]))) {
			run = 0;
			continue;
		}
		run++;
		if (run === 1) continue;
		if (run === 2) {
			long = close[i] >= close[i - 1];
			sar = long ? low[i - 1] : high[i - 1];
			ep = long ? Math.max(high[i - 1], h) : Math.min(low[i - 1], l);
			af = step;
			out[i] = sar;
			continue;
		}
		let next = sar + af * (ep - sar);
		if (long) {
			next = Math.min(next, low[i - 1], low[i - 2]);
			if (l < next) {
				long = false;
				next = ep;
				ep = l;
				af = step;
			} else if (h > ep) {
				ep = h;
				af = Math.min(af + step, maxStep);
			}
		} else {
			next = Math.max(next, high[i - 1], high[i - 2]);
			if (h > next) {
				long = true;
				next = ep;
				ep = h;
				af = step;
			} else if (l < ep) {
				ep = l;
				af = Math.min(af + step, maxStep);
			}
		}
		sar = next;
		out[i] = sar;
	}
	return out;
}

/**
 * Supertrend with Wilder ATR bands. Direction +1 = uptrend (value is the lower band), -1 =
 * downtrend (value is the upper band). The first bar with a valid ATR starts in the trend given
 * by close vs. HL2.
 */
function supertrend(
	high: Series,
	low: Series,
	close: Series,
	period: number,
	mult: number
): [Series, Series] {
	const n = high.length;
	const value = nanArray(n);
	const direction = nanArray(n);
	const atr = atrWilder(high, low, close, period);
	let live = false;
	let finalUpper = 0;
	let finalLower = 0;
	let dir = 1;
	for (let i = 0; i < n; i++) {
		if (!(nz(atr[i]) && nz(close[i]) && nz(high[i]) && nz(low[i]))) {
			live = false;
			continue;
		}
		const mid = (high[i] + low[i]) / 2;
		const upper = mid + mult * atr[i];
		const lower = mid - mult * atr[i];
		if (!live) {
			finalUpper = upper;
			finalLower = lower;
			dir = close[i] >= mid ? 1 : -1;
			live = true;
		} else {
			const prevClose = close[i - 1];
			finalUpper = upper < finalUpper || prevClose > finalUpper ? upper : finalUpper;
			finalLower = lower > finalLower || prevClose < finalLower ? lower : finalLower;
			if (dir === -1) dir = close[i] > finalUpper ? 1 : -1;
			else dir = close[i] < finalLower ? -1 : 1;
		}
		value[i] = dir === 1 ? finalLower : finalUpper;
		direction[i] = dir;
	}
	return [value, direction];
}

/** Wilder directional movement system. `+DI`/`-DI`/`ADX` use the backend-style Wilder seed. */
function directionalMovement(
	high: Series,
	low: Series,
	close: Series,
	period: number
): { adx: Series; plusDi: Series; minusDi: Series } {
	const n = high.length;
	const plusDm = nanArray(n);
	const minusDm = nanArray(n);
	for (let i = 1; i < n; i++) {
		const up = high[i] - high[i - 1];
		const down = low[i - 1] - low[i];
		plusDm[i] = up > down && up > 0 ? up : Number.isNaN(up + down) ? NaN : 0;
		minusDm[i] = down > up && down > 0 ? down : Number.isNaN(up + down) ? NaN : 0;
	}
	const tr = trueRange(high, low, close);
	if (n > 0) tr[0] = NaN;
	const smoothTr = wilder(tr, period);
	const plusDi = zip(wilder(plusDm, period), smoothTr, (m, t) => (t === 0 ? NaN : (100 * m) / t));
	const minusDi = zip(wilder(minusDm, period), smoothTr, (m, t) => (t === 0 ? NaN : (100 * m) / t));
	const dx = zip(plusDi, minusDi, (p, m) => (p + m === 0 ? 0 : (100 * Math.abs(p - m)) / (p + m)));
	return { adx: wilder(dx, period), plusDi, minusDi };
}

const trendGuides = [0] as const;

export const trendIndicators: IndicatorDefinition[] = [
	{
		id: 'sma',
		name: 'Simple Moving Average',
		short: 'SMA',
		description: 'Arithmetic mean of the last N closes.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'SMA')],
		compute: (d, p) => [rollingMean(d.close, p.period)]
	},
	{
		id: 'ema',
		name: 'Exponential Moving Average',
		short: 'EMA',
		description: 'Exponentially weighted average of closes with span N (alpha = 2 / (N + 1)).',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'EMA')],
		compute: (d, p) => [emaSpan(d.close, p.period)]
	},
	{
		id: 'wma',
		name: 'Weighted Moving Average',
		short: 'WMA',
		description: 'Linearly weighted average of the last N closes, newest bar weighted most.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'WMA')],
		compute: (d, p) => [wma(d.close, p.period)]
	},
	{
		id: 'dema',
		name: 'Double Exponential Moving Average',
		short: 'DEMA',
		description: 'Lag-reduced average computed as 2 * EMA - EMA(EMA).',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'DEMA')],
		compute: (d, p) => {
			const e1 = emaSpan(d.close, p.period);
			return [sub(scale(e1, 2), emaSpan(e1, p.period))];
		}
	},
	{
		id: 'tema',
		name: 'Triple Exponential Moving Average',
		short: 'TEMA',
		description: 'Lag-reduced average computed as 3 * EMA - 3 * EMA(EMA) + EMA(EMA(EMA)).',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'TEMA')],
		compute: (d, p) => {
			const e1 = emaSpan(d.close, p.period);
			const e2 = emaSpan(e1, p.period);
			const e3 = emaSpan(e2, p.period);
			return [add(sub(scale(e1, 3), scale(e2, 3)), e3)];
		}
	},
	{
		id: 'hma',
		name: 'Hull Moving Average',
		short: 'HMA',
		description: 'WMA of (2 * WMA(N/2) - WMA(N)) over sqrt(N) bars; a fast, smooth moving average.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'HMA')],
		compute: (d, p) => {
			const half = Math.max(1, Math.floor(p.period / 2));
			const root = Math.max(1, Math.round(Math.sqrt(p.period)));
			const raw = sub(scale(wma(d.close, half), 2), wma(d.close, p.period));
			return [wma(raw, root)];
		}
	},
	{
		id: 'kama',
		name: 'Kaufman Adaptive Moving Average',
		short: 'KAMA',
		description:
			'Moving average whose smoothing speeds up in efficient trends and slows in noise (efficiency ratio).',
		category: 'Trend',
		pane: 'price',
		params: [
			periodParam(10, 2),
			int('fast', 'Fast span', 2, 1, 100),
			int('slow', 'Slow span', 30, 2, 500)
		],
		outputs: [output('value', 'KAMA')],
		compute: (d, p) => [kama(d.close, p.period, p.fast, p.slow)]
	},
	{
		id: 'vwma',
		name: 'Volume Weighted Moving Average',
		short: 'VWMA',
		description: 'Average of the last N closes weighted by each bar volume.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'VWMA')],
		compute: (d, p) => [
			div(rollingSum(mul(d.close, d.volume), p.period), rollingSum(d.volume, p.period))
		]
	},
	{
		id: 'zlema',
		name: 'Zero-Lag Exponential Moving Average',
		short: 'ZLEMA',
		description:
			'EMA of a lag-compensated price (2 * close - close[lag]) to cut moving-average delay.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20, 2)],
		outputs: [output('value', 'ZLEMA')],
		compute: (d, p) => {
			const lag = Math.floor((p.period - 1) / 2);
			return [emaSpan(sub(scale(d.close, 2), shift(d.close, lag)), p.period)];
		}
	},
	{
		id: 't3',
		name: 'Tillson T3 Moving Average',
		short: 'T3',
		description:
			'Six-times smoothed EMA blend with a volume factor, giving a very smooth low-lag average.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(5, 1, 100), num('vfactor', 'Volume factor', 0.7, 0, 1, 0.05)],
		outputs: [output('value', 'T3')],
		compute: (d, p) => {
			const a = p.vfactor;
			const e1 = emaSpan(d.close, p.period);
			const e2 = emaSpan(e1, p.period);
			const e3 = emaSpan(e2, p.period);
			const e4 = emaSpan(e3, p.period);
			const e5 = emaSpan(e4, p.period);
			const e6 = emaSpan(e5, p.period);
			const c1 = -(a ** 3);
			const c2 = 3 * a ** 2 + 3 * a ** 3;
			const c3 = -6 * a ** 2 - 3 * a - 3 * a ** 3;
			const c4 = 1 + 3 * a + a ** 3 + 3 * a ** 2;
			const out = nanArray(d.close.length);
			for (let i = 0; i < out.length; i++) {
				out[i] = c1 * e6[i] + c2 * e5[i] + c3 * e4[i] + c4 * e3[i];
			}
			return [out];
		}
	},
	{
		id: 'smma',
		name: 'Smoothed Moving Average (Wilder)',
		short: 'SMMA',
		description: 'Wilder smoothing of closes (alpha = 1 / N), the average behind RSI, ATR and ADX.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(14)],
		outputs: [output('value', 'SMMA')],
		compute: (d, p) => [wilder(d.close, p.period)]
	},
	{
		id: 'trima',
		name: 'Triangular Moving Average',
		short: 'TRIMA',
		description: 'Double-smoothed SMA that weights the middle of the N-bar window most.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'TRIMA')],
		compute: (d, p) => {
			const odd = p.period % 2 === 1;
			const first = odd ? (p.period + 1) / 2 : p.period / 2;
			const second = odd ? first : first + 1;
			return [rollingMean(rollingMean(d.close, first), second)];
		}
	},
	{
		id: 'mcginley',
		name: 'McGinley Dynamic',
		short: 'MGD',
		description:
			'Self-adjusting moving average that speeds up or slows down with the price-to-average ratio.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(14, 2)],
		outputs: [output('value', 'McGinley')],
		compute: (d, p) => {
			const out = nanArray(d.close.length);
			let state = NaN;
			let obs = 0;
			for (let i = 0; i < out.length; i++) {
				const c = d.close[i];
				if (!nz(c)) continue;
				if (obs === 0 || !(state > 0)) state = c;
				else state += (c - state) / (0.6 * p.period * (c / state) ** 4);
				obs++;
				if (obs >= p.period) out[i] = state;
			}
			return [out];
		}
	},
	{
		id: 'rolling_vwap',
		name: 'Rolling VWAP',
		short: 'rVWAP',
		description: 'Volume-weighted average typical price over the last N bars.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('value', 'VWAP')],
		compute: (d, p) => [
			div(rollingSum(mul(typicalPrice(d), d.volume), p.period), rollingSum(d.volume, p.period))
		]
	},
	{
		id: 'vwap',
		name: 'Cumulative VWAP',
		short: 'VWAP',
		description: 'Volume-weighted average typical price accumulated from the first bar.',
		category: 'Trend',
		pane: 'price',
		params: [],
		outputs: [output('value', 'VWAP')],
		compute: (d) => {
			const n = d.close.length;
			const out = nanArray(n);
			let pv = 0;
			let vol = 0;
			for (let i = 0; i < n; i++) {
				const tp = (d.high[i] + d.low[i] + d.close[i]) / 3;
				const v = d.volume[i];
				if (!nz(tp) || !nz(v)) continue;
				pv += tp * v;
				vol += v;
				if (vol > 0) out[i] = pv / vol;
			}
			return [out];
		}
	},
	{
		id: 'bollinger',
		name: 'Bollinger Bands',
		short: 'BB',
		description: 'SMA of closes with bands at +/- k population standard deviations.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20), multParam(2)],
		outputs: [output('lower', 'Lower'), output('middle', 'Middle'), output('upper', 'Upper')],
		compute: (d, p) => {
			const mid = rollingMean(d.close, p.period);
			const dev = scale(rollingStd(d.close, p.period, 0), p.mult);
			return [sub(mid, dev), mid, add(mid, dev)];
		}
	},
	{
		id: 'bollinger_pctb',
		name: 'Bollinger %B',
		short: '%B',
		description:
			'Position of the close within the Bollinger Bands (0 = lower band, 1 = upper band).',
		category: 'Trend',
		pane: 'separate',
		guides: [0, 1],
		params: [periodParam(20), multParam(2)],
		outputs: VALUE,
		compute: (d, p) => {
			const mid = rollingMean(d.close, p.period);
			const dev = scale(rollingStd(d.close, p.period, 0), p.mult);
			const out = nanArray(d.close.length);
			for (let i = 0; i < out.length; i++) {
				if (!isDegenerate(dev[i], mid[i])) out[i] = (d.close[i] - mid[i] + dev[i]) / (2 * dev[i]);
			}
			return [out];
		}
	},
	{
		id: 'keltner',
		name: 'Keltner Channels',
		short: 'KC',
		description: 'EMA of closes with bands at +/- k Wilder ATRs.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20), int('atrPeriod', 'ATR period', 10, 1, 500), multParam(2)],
		outputs: [output('lower', 'Lower'), output('middle', 'Middle'), output('upper', 'Upper')],
		compute: (d, p) => {
			const mid = emaSpan(d.close, p.period);
			const band = scale(atrWilder(d.high, d.low, d.close, p.atrPeriod), p.mult);
			return [sub(mid, band), mid, add(mid, band)];
		}
	},
	{
		id: 'donchian',
		name: 'Donchian Channels',
		short: 'DC',
		description:
			'Highest high and lowest low of the last N bars (including the current bar) and their midpoint.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: [output('lower', 'Lower'), output('middle', 'Middle'), output('upper', 'Upper')],
		compute: (d, p) => {
			const upper = rollingMax(d.high, p.period);
			const lower = rollingMin(d.low, p.period);
			return [lower, scale(add(upper, lower), 0.5), upper];
		}
	},
	{
		id: 'psar',
		name: 'Parabolic SAR',
		short: 'PSAR',
		description: 'Trailing stop-and-reverse level that accelerates toward price during a trend.',
		category: 'Trend',
		pane: 'price',
		params: [
			num('step', 'Acceleration step', 0.02, 0.001, 0.5, 0.001),
			num('maxStep', 'Maximum acceleration', 0.2, 0.01, 1, 0.01)
		],
		outputs: VALUE,
		compute: (d, p) => [parabolicSar(d.high, d.low, d.close, p.step, p.maxStep)]
	},
	{
		id: 'supertrend',
		name: 'Supertrend',
		short: 'ST',
		description:
			'ATR-band trailing line that flips between the lower band (uptrend) and upper band (downtrend).',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(10), multParam(3)],
		outputs: VALUE,
		compute: (d, p) => [supertrend(d.high, d.low, d.close, p.period, p.mult)[0]]
	},
	{
		id: 'supertrend_direction',
		name: 'Supertrend Direction',
		short: 'ST dir',
		description:
			'Supertrend regime: +1 while price is above the trailing line (uptrend), -1 in a downtrend.',
		category: 'Trend',
		pane: 'separate',
		guides: trendGuides,
		params: [periodParam(10), multParam(3)],
		outputs: VALUE,
		compute: (d, p) => [supertrend(d.high, d.low, d.close, p.period, p.mult)[1]]
	},
	{
		id: 'linreg',
		name: 'Linear Regression Value',
		short: 'LinReg',
		description: 'End point of the least-squares line fitted to the last N closes.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20, 2)],
		outputs: VALUE,
		compute: (d, p) => [rollingRegression(d.close, p.period).value]
	},
	{
		id: 'linreg_slope',
		name: 'Linear Regression Slope',
		short: 'LR slope',
		description:
			'Slope (price change per bar) of the least-squares line fitted to the last N closes.',
		category: 'Trend',
		pane: 'separate',
		guides: trendGuides,
		params: [periodParam(20, 2)],
		outputs: VALUE,
		compute: (d, p) => [rollingRegression(d.close, p.period).slope]
	},
	{
		id: 'linreg_r2',
		name: 'Linear Regression R-squared',
		short: 'LR R²',
		description:
			'Share of close variance over the last N bars explained by a straight line (trend quality).',
		category: 'Trend',
		pane: 'separate',
		guides: [0.5],
		params: [periodParam(20, 2)],
		outputs: VALUE,
		compute: (d, p) => [rollingRegression(d.close, p.period).r2]
	},
	{
		id: 'ichimoku',
		name: 'Ichimoku Cloud (unshifted)',
		short: 'Ichimoku',
		description:
			'Tenkan, Kijun and Senkou A/B lines computed at the current bar with no forward displacement.',
		category: 'Trend',
		pane: 'price',
		params: [
			int('tenkan', 'Tenkan period', 9, 1, 200),
			int('kijun', 'Kijun period', 26, 1, 500),
			int('senkouB', 'Senkou B period', 52, 1, 500)
		],
		outputs: [
			output('tenkan', 'Tenkan-sen'),
			output('kijun', 'Kijun-sen'),
			output('senkou_a', 'Senkou Span A'),
			output('senkou_b', 'Senkou Span B')
		],
		compute: (d, p) => {
			const mid = (w: number) => scale(add(rollingMax(d.high, w), rollingMin(d.low, w)), 0.5);
			const tenkan = mid(p.tenkan);
			const kijun = mid(p.kijun);
			return [tenkan, kijun, scale(add(tenkan, kijun), 0.5), mid(p.senkouB)];
		}
	},
	{
		id: 'adx',
		name: 'Average Directional Index',
		short: 'ADX',
		description:
			'Trend strength (ADX) with the +DI and -DI directional indicators, Wilder smoothed.',
		category: 'Trend',
		pane: 'separate',
		guides: [20, 25],
		params: [periodParam(14, 2)],
		outputs: [output('adx', 'ADX'), output('plus_di', '+DI'), output('minus_di', '-DI')],
		compute: (d, p) => {
			const { adx, plusDi, minusDi } = directionalMovement(d.high, d.low, d.close, p.period);
			return [adx, plusDi, minusDi];
		}
	},
	{
		id: 'aroon',
		name: 'Aroon',
		short: 'Aroon',
		description:
			'Time since the highest high (up) and lowest low (down) within N bars, scaled 0-100.',
		category: 'Trend',
		pane: 'separate',
		guides: [50],
		params: [periodParam(25, 1, 400)],
		outputs: [
			output('up', 'Aroon Up'),
			output('down', 'Aroon Down'),
			output('osc', 'Aroon Oscillator')
		],
		compute: (d, p) => {
			const n = d.close.length;
			const hi = rollingArgMax(d.high, p.period + 1);
			const lo = rollingArgMin(d.low, p.period + 1);
			const up = nanArray(n);
			const down = nanArray(n);
			for (let i = 0; i < n; i++) {
				up[i] = (100 * (hi[i] - (i - p.period))) / p.period;
				down[i] = (100 * (lo[i] - (i - p.period))) / p.period;
			}
			return [up, down, sub(up, down)];
		}
	},
	{
		id: 'vortex',
		name: 'Vortex Indicator',
		short: 'VI',
		description:
			'Ratio of upward and downward bar-to-bar movement to true range over N bars (+VI / -VI).',
		category: 'Trend',
		pane: 'separate',
		guides: [1],
		params: [periodParam(14, 2)],
		outputs: [output('plus', '+VI'), output('minus', '-VI')],
		compute: (d, p) => {
			const n = d.close.length;
			const vmPlus = nanArray(n);
			const vmMinus = nanArray(n);
			for (let i = 1; i < n; i++) {
				vmPlus[i] = Math.abs(d.high[i] - d.low[i - 1]);
				vmMinus[i] = Math.abs(d.low[i] - d.high[i - 1]);
			}
			const tr = trueRange(d.high, d.low, d.close);
			if (n > 0) tr[0] = NaN;
			const trSum = rollingSum(tr, p.period);
			return [div(rollingSum(vmPlus, p.period), trSum), div(rollingSum(vmMinus, p.period), trSum)];
		}
	},
	{
		id: 'ma_distance',
		name: 'Price vs SMA Distance %',
		short: 'SMA dist',
		description: 'Percent distance of the close from its N-bar simple moving average.',
		category: 'Trend',
		pane: 'separate',
		guides: trendGuides,
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [pctDiff(d.close, rollingMean(d.close, p.period))]
	},
	{
		id: 'ema_distance',
		name: 'Price vs EMA Distance %',
		short: 'EMA dist',
		description: 'Percent distance of the close from its N-span exponential moving average.',
		category: 'Trend',
		pane: 'separate',
		guides: trendGuides,
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [pctDiff(d.close, emaSpan(d.close, p.period))]
	},
	{
		id: 'envelope',
		name: 'Moving Average Envelope',
		short: 'Env',
		description: 'SMA of closes with bands a fixed percentage above and below.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20), num('percent', 'Band %', 2.5, 0.01, 50, 0.05)],
		outputs: [output('lower', 'Lower'), output('middle', 'Middle'), output('upper', 'Upper')],
		compute: (d, p) => {
			const mid = rollingMean(d.close, p.period);
			return [scale(mid, 1 - p.percent / 100), mid, scale(mid, 1 + p.percent / 100)];
		}
	},
	{
		id: 'chandelier_exit',
		name: 'Chandelier Exit',
		short: 'CE',
		description:
			'ATR trailing stops: highest high minus k ATR (long) and lowest low plus k ATR (short).',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(22), multParam(3)],
		outputs: [output('long', 'Long stop'), output('short', 'Short stop')],
		compute: (d, p) => {
			const band = scale(atrWilder(d.high, d.low, d.close, p.period), p.mult);
			return [sub(rollingMax(d.high, p.period), band), add(rollingMin(d.low, p.period), band)];
		}
	},
	{
		id: 'median_price_ma',
		name: 'Median Price SMA',
		short: 'HL2 SMA',
		description: 'Simple moving average of the bar midpoint (high + low) / 2.',
		category: 'Trend',
		pane: 'price',
		params: [periodParam(20)],
		outputs: VALUE,
		compute: (d, p) => [rollingMean(medianPrice(d), p.period)]
	}
];
