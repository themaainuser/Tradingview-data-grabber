/** Hand-verifiable and invariant checks for individual indicators. */
import { describe, expect, it } from 'vitest';
import { alternateParams, makeOhlcv } from './fixtures';
import { computeIndicator, getIndicator } from './registry';
import type { OhlcvColumns } from './types';

const DATA = makeOhlcv(400, 11);
const CALM = makeOhlcv(600, 5);
const WILD = makeOhlcv(600, 6, 4);

const run = (id: string, overrides: Record<string, unknown> = {}, data: OhlcvColumns = DATA) => {
	const def = getIndicator(id);
	if (!def) throw new Error(`unknown indicator ${id}`);
	return computeIndicator(def, data, overrides);
};

/** Builds columns from `[open, high, low, close, volume]` rows. */
function bars(rows: number[][]): OhlcvColumns {
	const col = (k: number) => Float64Array.from(rows.map((r) => r[k]));
	return {
		time: Float64Array.from(rows.map((_, i) => i)),
		open: col(0),
		high: col(1),
		low: col(2),
		close: col(3),
		volume: col(4)
	};
}

/** `count` bars rising by one per bar with range 1 (high = close, low = close - 1). */
const ramp = (count: number, step = 1): OhlcvColumns =>
	bars(
		Array.from({ length: count }, (_, i) => {
			const c = 100 + i * step;
			return [c - step / 2, c, c - 1, c, 1000];
		})
	);

const ramp1 = (count: number) => ramp(count);
const fall = (count: number): OhlcvColumns =>
	bars(
		Array.from({ length: count }, (_, i) => {
			const c = 200 - i;
			return [c + 0.5, c + 1, c, c, 1000];
		})
	);

const list = (a: Float64Array) => Array.from(a);
const finite = (a: Float64Array) => list(a).filter(Number.isFinite);
const at = (a: Float64Array, i: number) => a[i < 0 ? a.length + i : i];
function expectClose(actual: Float64Array, expected: number[], digits = 9) {
	expect(actual).toHaveLength(expected.length);
	expected.forEach((e, i) => {
		if (Number.isNaN(e)) expect(actual[i], `index ${i}`).toBeNaN();
		else expect(actual[i], `index ${i}`).toBeCloseTo(e, digits);
	});
}

describe('values stay inside their mathematical bounds', () => {
	const BOUNDS: [id: string, output: number, lo: number, hi: number][] = [
		['rsi', 0, 0, 100],
		['stochastic', 0, 0, 100],
		['stochastic', 1, 0, 100],
		['stoch_rsi', 0, 0, 100],
		['stoch_rsi', 1, 0, 100],
		['williams_r', 0, -100, 0],
		['mfi', 0, 0, 100],
		['adx', 0, 0, 100],
		['adx', 1, 0, 100],
		['adx', 2, 0, 100],
		['aroon', 0, 0, 100],
		['aroon', 1, 0, 100],
		['aroon', 2, -100, 100],
		['cmf', 0, -1, 1],
		['cmo', 0, -100, 100],
		['tsi', 0, -100, 100],
		['ultimate_oscillator', 0, 0, 100],
		['connors_rsi', 0, 0, 100],
		['connors_rsi', 1, 0, 100],
		['connors_rsi', 2, 0, 100],
		['connors_rsi', 3, 0, 100],
		['percent_rank', 0, 0, 100],
		['up_bar_ratio', 0, 0, 100],
		['choppiness', 0, 0, 100],
		['bop', 0, -1, 1],
		['body_pct', 0, -100, 100],
		['upper_wick_pct', 0, 0, 100],
		['lower_wick_pct', 0, 0, 100],
		['clv', 0, -1, 1],
		['linreg_r2', 0, 0, 1],
		['autocorrelation', 0, -1, 1],
		['drawdown', 0, -100, 0],
		['max_drawdown', 0, -100, 0],
		['distance_from_high', 0, -100, 0],
		['distance_from_low', 0, 0, Infinity],
		['vortex', 0, 0, Infinity],
		['vortex', 1, 0, Infinity],
		['true_range', 0, 0, Infinity],
		['atr', 0, 0, Infinity],
		['atr_wilder', 0, 0, Infinity],
		['natr', 0, 0, Infinity],
		['stdev_returns', 0, 0, Infinity],
		['hist_vol', 0, 0, Infinity],
		['parkinson', 0, 0, Infinity],
		['garman_klass', 0, 0, Infinity],
		['rogers_satchell', 0, 0, Infinity],
		['yang_zhang', 0, 0, Infinity],
		['ewma_vol', 0, 0, Infinity],
		['ulcer_index', 0, 0, Infinity],
		['bollinger_bandwidth', 0, 0, Infinity],
		['donchian_width', 0, 0, Infinity],
		['volume_sma', 0, 0, Infinity],
		['relative_volume', 0, 0, Infinity],
		['dollar_volume', 0, 0, Infinity]
	];
	const eps = 1e-9;
	it.each(BOUNDS)('%s output %i within [%d, %d]', (id, output, lo, hi) => {
		const def = getIndicator(id)!;
		for (const data of [CALM, WILD]) {
			for (const overrides of [{}, alternateParams(def)]) {
				const values = finite(run(id, overrides, data)[output]);
				expect(values.length, `${id} produced values`).toBeGreaterThan(50);
				expect(Math.min(...values)).toBeGreaterThanOrEqual(lo - eps);
				expect(Math.max(...values)).toBeLessThanOrEqual(hi + eps);
			}
		}
	});
});

describe('band and channel structure', () => {
	it('Bollinger bands are symmetric around the SMA and match a population-std brute force', () => {
		const [lower, middle, upper] = run('bollinger', { period: 20, mult: 2 });
		const sma = run('sma', { period: 20 })[0];
		for (let i = 19; i < DATA.close.length; i++) {
			expect(upper[i] - middle[i]).toBeCloseTo(middle[i] - lower[i], 9);
			expect(lower[i]).toBeLessThanOrEqual(middle[i]);
			expect(middle[i]).toBe(sma[i]);
		}
		const i = 250;
		const window = Array.from(DATA.close.subarray(i - 19, i + 1));
		const mean = window.reduce((a, b) => a + b, 0) / 20;
		const std = Math.sqrt(window.reduce((a, b) => a + (b - mean) ** 2, 0) / 20);
		expect(upper[i]).toBeCloseTo(mean + 2 * std, 9);
		expect(lower[i]).toBeCloseTo(mean - 2 * std, 9);
		expect(lower[18]).toBeNaN();
	});

	it('Bollinger %B and bandwidth are consistent with the bands', () => {
		const [lower, middle, upper] = run('bollinger', { period: 20, mult: 2 });
		const pctB = run('bollinger_pctb', { period: 20, mult: 2 })[0];
		const width = run('bollinger_bandwidth', { period: 20, mult: 2 })[0];
		for (const i of [19, 100, 300]) {
			expect(pctB[i]).toBeCloseTo((DATA.close[i] - lower[i]) / (upper[i] - lower[i]), 9);
			expect(width[i]).toBeCloseTo((100 * (upper[i] - lower[i])) / middle[i], 9);
		}
	});

	it('Donchian channels are ordered and bracket the price', () => {
		const [lower, middle, upper] = run('donchian', { period: 20 });
		for (let i = 19; i < DATA.close.length; i++) {
			expect(lower[i]).toBeLessThanOrEqual(middle[i]);
			expect(middle[i]).toBeLessThanOrEqual(upper[i]);
			expect(upper[i]).toBeGreaterThanOrEqual(DATA.high[i]);
			expect(lower[i]).toBeLessThanOrEqual(DATA.low[i]);
		}
		const width = run('donchian_width', { period: 20 })[0];
		expect(width[100]).toBeCloseTo((100 * (upper[100] - lower[100])) / middle[100], 9);
	});

	it('Keltner channels and envelopes are ordered and symmetric', () => {
		const [kl, km, ku] = run('keltner');
		const [el, em, eu] = run('envelope', { percent: 2.5 });
		for (let i = 30; i < DATA.close.length; i++) {
			expect(kl[i]).toBeLessThan(km[i]);
			expect(ku[i] - km[i]).toBeCloseTo(km[i] - kl[i], 9);
			expect(eu[i] - em[i]).toBeCloseTo(em[i] - el[i], 9);
			expect(eu[i] / em[i]).toBeCloseTo(1.025, 12);
		}
	});

	it('Ichimoku lines use only past bars (no forward shift)', () => {
		const [tenkan, kijun, spanA, spanB] = run('ichimoku', { tenkan: 9, kijun: 26, senkouB: 52 });
		const mid = (i: number, w: number) => {
			const hi = Math.max(...DATA.high.subarray(i - w + 1, i + 1));
			const lo = Math.min(...DATA.low.subarray(i - w + 1, i + 1));
			return (hi + lo) / 2;
		};
		for (const i of [51, 100, 399]) {
			expect(tenkan[i]).toBeCloseTo(mid(i, 9), 12);
			expect(kijun[i]).toBeCloseTo(mid(i, 26), 12);
			expect(spanA[i]).toBeCloseTo((mid(i, 9) + mid(i, 26)) / 2, 12);
			expect(spanB[i]).toBeCloseTo(mid(i, 52), 12);
		}
		expect(spanB[50]).toBeNaN();
		expect(spanB[51]).not.toBeNaN();
	});
});

describe('oscillator identities', () => {
	it('MACD histogram equals MACD minus signal, and MACD equals EMA(fast) - EMA(slow)', () => {
		const [macd, signal, hist] = run('macd');
		const fast = run('ema', { period: 12 })[0];
		const slow = run('ema', { period: 26 })[0];
		for (let i = 0; i < DATA.close.length; i++) {
			if (i >= 25) expect(macd[i]).toBeCloseTo(fast[i] - slow[i], 12);
			if (i >= 33) expect(hist[i]).toBeCloseTo(macd[i] - signal[i], 12);
			else expect(hist[i]).toBeNaN();
		}
		expect(list(macd).findIndex(Number.isFinite)).toBe(25);
		expect(list(signal).findIndex(Number.isFinite)).toBe(33);
	});

	it('PPO is MACD as a percent of the slow EMA', () => {
		const macd = run('macd')[0];
		const slow = run('ema', { period: 26 })[0];
		const ppo = run('ppo')[0];
		for (const i of [25, 100, 399]) expect(ppo[i]).toBeCloseTo((100 * macd[i]) / slow[i], 9);
		expect(run('apo')[0][100]).toBeCloseTo(macd[100], 12);
	});

	it('RSI hits 100, 0 and 50 for pure gains, pure losses and flat prices', () => {
		const rsi = (data: OhlcvColumns) => run('rsi', { period: 5 }, data)[0];
		expect(at(rsi(ramp1(30)), -1)).toBe(100);
		expect(at(rsi(fall(30)), -1)).toBe(0);
		const flat = bars(Array.from({ length: 30 }, () => [50, 50, 50, 50, 10]));
		expect(at(rsi(flat), -1)).toBe(50);
	});

	it('Stochastic, Williams %R and Aroon saturate at a fresh N-bar extreme', () => {
		const up = ramp1(30);
		const [k, d] = run('stochastic', { period: 5, kSmooth: 1, dPeriod: 1 }, up);
		expect(at(k, -1)).toBeCloseTo(100, 9);
		expect(at(d, -1)).toBeCloseTo(100, 9);
		expect(at(run('williams_r', { period: 5 }, up)[0], -1)).toBeCloseTo(0, 9);
		const [aroonUp, aroonDown, aroonOsc] = run('aroon', { period: 5 }, up);
		expect(at(aroonUp, -1)).toBe(100);
		expect(at(aroonDown, -1)).toBe(0);
		expect(at(aroonOsc, -1)).toBe(100);
		expect(aroonUp[4]).toBeNaN();
		expect(aroonUp[5]).toBe(100);
		const down = fall(30);
		expect(at(run('williams_r', { period: 5 }, down)[0], -1)).toBeCloseTo(-100, 9);
		expect(at(run('aroon', { period: 5 }, down)[1], -1)).toBe(100);
	});

	it('directional indicators identify a clean trend', () => {
		const [adx, plus, minus] = run('adx', { period: 5 }, ramp1(40));
		expect(at(plus, -1)).toBeCloseTo(100, 9);
		expect(at(minus, -1)).toBeCloseTo(0, 9);
		expect(at(adx, -1)).toBeCloseTo(100, 9);
		const [vp, vm] = run('vortex', { period: 5 }, ramp1(40));
		expect(at(vp, -1)).toBeCloseTo(2, 9);
		expect(at(vm, -1)).toBeCloseTo(0, 9);
		const [dnAdx, dnPlus, dnMinus] = run('adx', { period: 5 }, fall(40));
		expect(at(dnPlus, -1)).toBeCloseTo(0, 9);
		expect(at(dnMinus, -1)).toBeGreaterThan(90);
		expect(at(dnAdx, -1)).toBeGreaterThan(90);
	});

	it('momentum and rate of change on hand-checkable closes', () => {
		const data = bars([10, 11, 12, 15].map((c) => [c, c, c, c, 1]));
		expect(list(run('momentum', { period: 2 }, data)[0])).toEqual([NaN, NaN, 2, 4]);
		const roc = run('roc', { period: 2 }, data)[0];
		expect(roc[2]).toBeCloseTo(20, 12);
		expect(roc[3]).toBeCloseTo(100 * (15 / 11 - 1), 12);
		expect(run('rolling_return', { period: 2 }, data)[0][3]).toBeCloseTo(roc[3], 12);
	});

	it('TSI, CMO, CCI and DPO give exact values on a straight ramp', () => {
		const up = ramp1(80);
		expect(at(run('tsi', { long: 6, short: 3 }, up)[0], -1)).toBeCloseTo(100, 9);
		expect(at(run('cmo', { period: 5 }, up)[0], -1)).toBeCloseTo(100, 12);
		expect(at(run('cmo', { period: 5 }, fall(30))[0], -1)).toBeCloseTo(-100, 12);
		// typical price rises by one per bar, so tp - SMA(4) = 1.5 and mean deviation = 1
		expect(at(run('cci', { period: 4 }, up)[0], -1)).toBeCloseTo(1.5 / 0.015, 9);
		// close[i-3] - SMA4 = (i - 3) - (i - 1.5)
		expect(at(run('dpo', { period: 4 }, up)[0], -1)).toBeCloseTo(-1.5, 12);
	});
});

describe('volatility and range', () => {
	const gapping = bars([
		[10, 11, 9, 10, 1],
		[15, 16, 14, 15, 1],
		[8, 9, 7, 8, 1],
		[8.4, 9, 8, 8.5, 1]
	]);

	it('true range includes gaps against the previous close', () => {
		// bar1 gaps up (|16 - 10| = 6), bar2 gaps down (|7 - 15| = 8), bar3 is inside (range 1)
		expect(list(run('true_range', {}, gapping)[0])).toEqual([2, 6, 8, 1]);
	});

	it('ATR (SMA) and Wilder ATR follow their smoothing rules on gapping bars', () => {
		expect(list(run('atr', { period: 2 }, gapping)[0])).toEqual([NaN, 4, 7, 4.5]);
		expect(list(run('atr_wilder', { period: 2 }, gapping)[0])).toEqual([NaN, 4, 6, 3.5]);
		expect(run('natr', { period: 2 }, gapping)[0][3]).toBeCloseTo((100 * 3.5) / 8.5, 12);
		expect(run('range_atr', { period: 2 }, gapping)[0][3]).toBeCloseTo(1 / 3.5, 12);
	});

	it('range estimators equal their closed forms on a constant-range bar', () => {
		const ratio = 1.02;
		const flatBars = bars(Array.from({ length: 12 }, () => [100, 100 * ratio, 100, 100, 1]));
		const parkinson = run('parkinson', { window: 5, periodsPerYear: 1 }, flatBars)[0];
		expect(at(parkinson, -1)).toBeCloseTo((100 * Math.log(ratio)) / Math.sqrt(4 * Math.LN2), 10);
		const geometric = bars(
			Array.from({ length: 30 }, (_, i) => {
				const c = 100 * 1.01 ** i;
				return [c, c, c, c, 1];
			})
		);
		expect(at(run('hist_vol', { window: 10 }, geometric)[0], -1)).toBeLessThan(1e-9);
	});

	it('Ulcer index is the RMS of drawdowns from the window peak', () => {
		const data = bars([100, 90, 100].map((c) => [c, c, c, c, 1]));
		const out = run('ulcer_index', { period: 2 }, data)[0];
		expect(out[1]).toBeNaN();
		expect(out[2]).toBeCloseTo(Math.sqrt((100 + 0) / 2), 12);
	});

	it('Choppiness is 0 in a straight trend and 100 in a same-range zig-zag', () => {
		expect(at(run('choppiness', { period: 14 }, ramp1(40))[0], -1)).toBeCloseTo(0, 6);
		const zigzag = bars(Array.from({ length: 40 }, (_, i) => [100, 101, 99, i % 2 ? 101 : 99, 1]));
		expect(at(run('choppiness', { period: 14 }, zigzag)[0], -1)).toBeCloseTo(100, 9);
	});

	it('Parabolic SAR trails below a steady uptrend and never decreases', () => {
		const sar = run('psar', {}, ramp1(60))[0];
		const data = ramp1(60);
		expect(sar[0]).toBeNaN();
		for (let i = 1; i < 60; i++) {
			expect(sar[i]).toBeLessThan(data.low[i]);
			if (i > 1) expect(sar[i]).toBeGreaterThanOrEqual(sar[i - 1]);
		}
	});

	it('Supertrend flags uptrends (+1, below price) and downtrends (-1, above price)', () => {
		const up = ramp1(60);
		const upDir = run('supertrend_direction', { period: 5, mult: 2 }, up)[0];
		const upLine = run('supertrend', { period: 5, mult: 2 }, up)[0];
		expect(at(upDir, -1)).toBe(1);
		expect(at(upLine, -1)).toBeLessThan(at(up.close, -1));
		const down = fall(60);
		expect(at(run('supertrend_direction', { period: 5, mult: 2 }, down)[0], -1)).toBe(-1);
		expect(at(run('supertrend', { period: 5, mult: 2 }, down)[0], -1)).toBeGreaterThan(
			at(down.close, -1)
		);
		for (const v of finite(run('supertrend_direction', {}, WILD)[0])) expect(Math.abs(v)).toBe(1);
	});
});

describe('moving averages', () => {
	it('all price-scale averages return a constant for a constant price', () => {
		const flat = makeOhlcv(200, 8);
		for (const col of ['open', 'high', 'low', 'close'] as const) flat[col].fill(100);
		for (const id of [
			'sma',
			'ema',
			'wma',
			'dema',
			'tema',
			'hma',
			'kama',
			'vwma',
			'zlema',
			't3',
			'smma',
			'trima',
			'mcginley',
			'rolling_vwap',
			'vwap',
			'linreg',
			'median_price_ma',
			'keltner'
		]) {
			const out = run(id, {}, flat);
			const value = out[id === 'keltner' ? 1 : 0];
			expect(at(value, -1), id).toBeCloseTo(100, 8);
		}
	});

	it('rolling VWAP over the whole history equals cumulative VWAP', () => {
		const cumulative = run('vwap')[0];
		const rolling = run('rolling_vwap', { period: 60 })[0];
		expect(rolling[59]).toBeCloseTo(cumulative[59], 9);
		expect(rolling[58]).toBeNaN();
	});

	it('cumulative VWAP is undefined until volume trades', () => {
		const data = bars([
			[10, 10, 10, 10, 0],
			[10, 12, 8, 10, 100]
		]);
		expect(list(run('vwap', {}, data)[0])).toEqual([NaN, 10]);
	});

	it('HMA, DEMA and TEMA lag less than the SMA/EMA of the same length on a ramp', () => {
		const up = ramp1(120);
		const error = (id: string) => Math.abs(at(run(id, { period: 20 }, up)[0], -1) - 219);
		expect(error('hma')).toBeLessThan(error('sma'));
		expect(error('dema')).toBeLessThan(error('ema'));
		expect(error('tema')).toBeLessThan(error('ema'));
		expect(error('zlema')).toBeLessThan(error('ema'));
	});

	it('linear regression reproduces an exact line', () => {
		const up = ramp1(40);
		expect(at(run('linreg', { period: 10 }, up)[0], -1)).toBeCloseTo(139, 9);
		expect(at(run('linreg_slope', { period: 10 }, up)[0], -1)).toBeCloseTo(1, 12);
		expect(at(run('linreg_r2', { period: 10 }, up)[0], -1)).toBeCloseTo(1, 9);
	});

	it('distance indicators agree with the averages they reference', () => {
		const sma = run('sma', { period: 20 })[0];
		const ema = run('ema', { period: 20 })[0];
		const dist = run('ma_distance', { period: 20 })[0];
		const edist = run('ema_distance', { period: 20 })[0];
		for (const i of [19, 200, 399]) {
			expect(dist[i]).toBeCloseTo(100 * (DATA.close[i] / sma[i] - 1), 10);
			expect(edist[i]).toBeCloseTo(100 * (DATA.close[i] / ema[i] - 1), 10);
		}
	});
});

describe('volume indicators', () => {
	it('OBV adds volume on up closes and subtracts it on down closes', () => {
		const data = bars(
			[
				[10, 100],
				[11, 200],
				[10.5, 300],
				[10.5, 400],
				[12, 500]
			].map(([c, v]) => [c, c, c, c, v])
		);
		expect(list(run('obv', {}, data)[0])).toEqual([0, 200, -100, -100, 400]);
	});

	it('PVT, NVI and PVI follow their update rules', () => {
		const pvt = bars(
			[
				[10, 100],
				[11, 200],
				[10, 300]
			].map(([c, v]) => [c, c, c, c, v])
		);
		const out = run('pvt', {}, pvt)[0];
		expect(out[1]).toBeCloseTo(20, 12);
		expect(out[2]).toBeCloseTo(20 + 300 * (10 / 11 - 1), 12);
		const idx = bars(
			[
				[10, 100],
				[11, 200],
				[12, 150],
				[13, 150]
			].map(([c, v]) => [c, c, c, c, v])
		);
		expect(list(run('nvi', {}, idx)[0])).toEqual([1000, 1000, 1000 * (12 / 11), 1000 * (12 / 11)]);
		expect(list(run('pvi', {}, idx)[0])).toEqual([
			1000,
			1000 * (11 / 10),
			1000 * (11 / 10),
			1000 * (11 / 10)
		]);
	});

	it('A/D line and CMF react to where the close sits in the range', () => {
		const atHigh = bars(Array.from({ length: 30 }, () => [9, 10, 8, 10, 100]));
		const atLow = bars(Array.from({ length: 30 }, () => [9, 10, 8, 8, 100]));
		expect(at(run('ad_line', {}, atHigh)[0], -1)).toBe(3000);
		expect(at(run('ad_line', {}, atLow)[0], -1)).toBe(-3000);
		expect(at(run('cmf', { period: 20 }, atHigh)[0], -1)).toBeCloseTo(1, 12);
		expect(at(run('cmf', { period: 20 }, atLow)[0], -1)).toBeCloseTo(-1, 12);
		const zeroRange = bars(Array.from({ length: 5 }, () => [10, 10, 10, 10, 100]));
		expect(at(run('ad_line', {}, zeroRange)[0], -1)).toBe(0);
	});

	it('MFI is 100 for rising, 0 for falling and 50 for unchanged typical prices', () => {
		expect(at(run('mfi', { period: 5 }, ramp1(30))[0], -1)).toBe(100);
		expect(at(run('mfi', { period: 5 }, fall(30))[0], -1)).toBe(0);
		const flat = bars(Array.from({ length: 30 }, () => [50, 50, 50, 50, 10]));
		expect(at(run('mfi', { period: 5 }, flat)[0], -1)).toBe(50);
	});

	it('relative volume and volume ROC use trailing volume only', () => {
		const data = bars([1, 2, 3, 4].map((v) => [1, 1, 1, 1, v]));
		const rvol = run('relative_volume', { period: 2 }, data)[0];
		expectClose(rvol, [NaN, 2 / 1.5, 3 / 2.5, 4 / 3.5], 12);
		expectClose(run('volume_roc', { period: 1 }, data)[0], [NaN, 100, 50, 100 / 3], 9);
	});

	it('Klinger and Chaikin oscillators warm up on their slowest average', () => {
		expect(list(run('klinger')[0]).findIndex(Number.isFinite)).toBe(55);
		expect(list(run('klinger')[1]).findIndex(Number.isFinite)).toBe(67);
		expect(list(run('chaikin_osc')[0]).findIndex(Number.isFinite)).toBe(9);
	});
});

describe('statistics', () => {
	it('drawdown from the running peak and rolling max drawdown', () => {
		const data = bars([100, 110, 99, 120, 90].map((c) => [c, c, c, c, 1]));
		const dd = run('drawdown', {}, data)[0];
		expectClose(dd, [0, 0, -10, 0, -25], 9);
		const mdd = run('max_drawdown', { window: 3 }, data)[0];
		expectClose(mdd, [NaN, NaN, -10, -10, -25], 9);
		for (const v of finite(run('drawdown', {}, WILD)[0])) expect(v).toBeLessThanOrEqual(0);
	});

	it('simple and log returns', () => {
		const data = bars([100, 110, 99].map((c) => [c, c, c, c, 1]));
		const simple = run('simple_return', {}, data)[0];
		const log = run('log_return', {}, data)[0];
		expect(simple[0]).toBeNaN();
		expect(simple[1]).toBeCloseTo(10, 12);
		expect(simple[2]).toBeCloseTo(-10, 12);
		expect(log[1]).toBeCloseTo(100 * Math.log(1.1), 12);
	});

	it('z-score of a linear ramp is constant and rank saturates at 100', () => {
		const up = ramp1(60);
		const z = run('zscore', { window: 10 }, up)[0];
		expect(at(z, -1)).toBeCloseTo(at(z, -2), 9);
		expect(at(run('percent_rank', { window: 10 }, up)[0], -1)).toBe(100);
		expect(at(run('percent_rank', { window: 10 }, fall(60))[0], -1)).toBe(0);
	});

	it('N-bar extremes and distances', () => {
		const hh = run('highest_high', { period: 20 })[0];
		const ll = run('lowest_low', { period: 20 })[0];
		const dh = run('distance_from_high', { period: 20 })[0];
		const dl = run('distance_from_low', { period: 20 })[0];
		for (const i of [19, 150, 399]) {
			expect(hh[i]).toBe(Math.max(...DATA.high.subarray(i - 19, i + 1)));
			expect(ll[i]).toBe(Math.min(...DATA.low.subarray(i - 19, i + 1)));
			expect(dh[i]).toBeCloseTo(100 * (DATA.close[i] / hh[i] - 1), 10);
			expect(dl[i]).toBeCloseTo(100 * (DATA.close[i] / ll[i] - 1), 10);
		}
		expect(hh[18]).toBeNaN();
	});

	it('skew, kurtosis and autocorrelation need their minimum sample', () => {
		expect(list(run('skew', { window: 4 })[0]).findIndex(Number.isFinite)).toBe(4);
		expect(list(run('kurtosis', { window: 5 })[0]).findIndex(Number.isFinite)).toBe(5);
		expect(list(run('autocorrelation', { window: 10, lag: 3 })[0]).findIndex(Number.isFinite)).toBe(
			13
		);
	});

	it('Sharpe is undefined (not infinite) when returns have no dispersion', () => {
		const flat = bars(Array.from({ length: 80 }, () => [50, 50, 50, 50, 1]));
		expect(run('sharpe', { window: 20 }, flat)[0].every(Number.isNaN)).toBe(true);
	});
});

describe('price transforms', () => {
	const row = [10, 14, 8, 12, 100];
	const one = bars([row, [12, 15, 11, 11.5, 100]]);

	it('computes the standard price averages', () => {
		expect(run('typical_price', {}, one)[0][0]).toBeCloseTo((14 + 8 + 12) / 3, 12);
		expect(run('median_price', {}, one)[0][0]).toBe(11);
		expect(run('weighted_close', {}, one)[0][0]).toBe((14 + 8 + 24) / 4);
		expect(run('ohlc4', {}, one)[0][0]).toBe((10 + 14 + 8 + 12) / 4);
	});

	it('describes candle shape as percent of the range', () => {
		expect(run('range_pct', {}, one)[0][0]).toBeCloseTo((100 * 6) / 12, 12);
		expect(run('body_pct', {}, one)[0][0]).toBeCloseTo((100 * 2) / 6, 12);
		expect(run('upper_wick_pct', {}, one)[0][0]).toBeCloseTo((100 * 2) / 6, 12);
		expect(run('lower_wick_pct', {}, one)[0][0]).toBeCloseTo((100 * 2) / 6, 12);
		expect(run('clv', {}, one)[0][0]).toBeCloseTo((2 * 12 - 14 - 8) / 6, 12);
		expect(run('intraday_return', {}, one)[0][0]).toBeCloseTo(20, 12);
	});

	it('body and wicks always partition the bar range', () => {
		const [body] = run('body_pct', {}, WILD);
		const [upper] = run('upper_wick_pct', {}, WILD);
		const [lower] = run('lower_wick_pct', {}, WILD);
		for (let i = 0; i < WILD.close.length; i++) {
			expect(Math.abs(body[i]) + upper[i] + lower[i]).toBeCloseTo(100, 9);
		}
	});

	it('measures the gap and close change against the previous close', () => {
		expect(list(run('gap_pct', {}, one)[0])).toEqual([NaN, 100 * (12 / 12 - 1)]);
		const twoGap = bars([
			[10, 11, 9, 10, 1],
			[11, 12, 10, 11.5, 1]
		]);
		expect(run('gap_pct', {}, twoGap)[0][1]).toBeCloseTo(10, 12);
		expect(list(run('price_change', {}, twoGap)[0])).toEqual([NaN, 1.5]);
	});

	it('reports zero-range bars as undefined for shape ratios and neutral for CLV', () => {
		const flat = bars([[5, 5, 5, 5, 1]]);
		for (const id of ['body_pct', 'upper_wick_pct', 'lower_wick_pct']) {
			expect(run(id, {}, flat)[0][0]).toBeNaN();
		}
		expect(run('clv', {}, flat)[0][0]).toBe(0);
	});
});
