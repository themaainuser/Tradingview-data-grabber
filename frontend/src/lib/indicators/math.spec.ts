import { describe, expect, it } from 'vitest';
import { mulberry32 } from './fixtures';
import {
	ema,
	emaSpan,
	finiteRun,
	rollingArgMax,
	rollingArgMin,
	rollingAutocorrelation,
	rollingKurtosis,
	rollingMax,
	rollingMean,
	rollingMin,
	rollingPercentRank,
	rollingRegression,
	rollingSkew,
	rollingStd,
	rollingSum,
	rollingVariance,
	rsi,
	shift,
	trueRange,
	wilder,
	wma
} from './math';

const close = (a: number, b: number, tol = 1e-9) =>
	(Number.isNaN(a) && Number.isNaN(b)) ||
	Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b));

function expectSeriesClose(actual: Float64Array, expected: ArrayLike<number>, tol = 1e-9) {
	expect(actual).toHaveLength(expected.length);
	const bad: string[] = [];
	for (let i = 0; i < expected.length; i++) {
		if (!close(actual[i], expected[i], tol)) bad.push(`[${i}] ${actual[i]} != ${expected[i]}`);
	}
	expect(bad.slice(0, 5)).toEqual([]);
}

/** Random series with a few NaN/Infinity holes to exercise reset-and-recover behaviour. */
function noisy(n: number, seed: number, holes: number[] = []): Float64Array {
	const rand = mulberry32(seed);
	const out = new Float64Array(n);
	for (let i = 0; i < n; i++) out[i] = 50 + rand() * 20 - 10;
	holes.forEach((h, k) => (out[h] = k % 2 === 0 ? NaN : Infinity));
	return out;
}

function brute(src: Float64Array, w: number, fn: (window: number[]) => number): Float64Array {
	const out = new Float64Array(src.length).fill(NaN);
	for (let i = w - 1; i < src.length; i++) {
		const window = Array.from(src.subarray(i - w + 1, i + 1));
		if (window.every(Number.isFinite)) out[i] = fn(window);
	}
	return out;
}

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
const variance = (xs: number[], ddof: number) => {
	const m = sum(xs) / xs.length;
	return sum(xs.map((x) => (x - m) ** 2)) / (xs.length - ddof);
};

const CLEAN = noisy(600, 1);
const HOLEY = noisy(600, 2, [40, 41, 200, 333, 334, 335, 599]);

describe('rolling window primitives match brute force', () => {
	for (const [label, data] of [
		['clean', CLEAN],
		['with NaN/Infinity holes', HOLEY]
	] as const) {
		for (const w of [1, 2, 5, 20, 64]) {
			it(`sum/mean/std/max/min/argmax w=${w} (${label})`, () => {
				expectSeriesClose(rollingSum(data, w), brute(data, w, sum));
				expectSeriesClose(
					rollingMean(data, w),
					brute(data, w, (x) => sum(x) / w)
				);
				expectSeriesClose(
					rollingMax(data, w),
					brute(data, w, (x) => Math.max(...x))
				);
				expectSeriesClose(
					rollingMin(data, w),
					brute(data, w, (x) => Math.min(...x))
				);
				if (w > 1) {
					expectSeriesClose(
						rollingVariance(data, w, 0),
						brute(data, w, (x) => variance(x, 0))
					);
					expectSeriesClose(
						rollingStd(data, w, 1),
						brute(data, w, (x) => Math.sqrt(variance(x, 1)))
					);
				}
				const argmax = brute(data, w, (x) => x.lastIndexOf(Math.max(...x)));
				const got = rollingArgMax(data, w);
				for (let i = 0; i < data.length; i++) {
					const expected = Number.isNaN(argmax[i]) ? NaN : argmax[i] + i - w + 1;
					expect(close(got[i], expected)).toBe(true);
				}
				const argmin = brute(data, w, (x) => x.lastIndexOf(Math.min(...x)));
				const gotMin = rollingArgMin(data, w);
				for (let i = 0; i < data.length; i++) {
					const expected = Number.isNaN(argmin[i]) ? NaN : argmin[i] + i - w + 1;
					expect(close(gotMin[i], expected)).toBe(true);
				}
			});
		}
	}

	it('wma matches brute-force linear weights, including after holes', () => {
		for (const w of [1, 3, 10, 30]) {
			const weights = Array.from({ length: w }, (_, k) => k + 1);
			const expected = brute(HOLEY, w, (x) => sum(x.map((v, k) => v * weights[k])) / sum(weights));
			expectSeriesClose(wma(HOLEY, w), expected);
		}
	});

	it('ema/wilder match the pandas adjust=False recursion incl. leading NaN and min_periods', () => {
		const src = new Float64Array([NaN, NaN, 10, 11, 13, 12, 15, 14, 16]);
		const alpha = 0.3;
		const expected: number[] = [];
		let state = NaN;
		let obs = 0;
		for (const x of src) {
			if (Number.isNaN(x)) {
				expected.push(NaN);
				continue;
			}
			state = obs === 0 ? x : (1 - alpha) * state + alpha * x;
			obs++;
			expected.push(obs >= 3 ? state : NaN);
		}
		expectSeriesClose(ema(src, alpha, 3), expected);
		// span=5 -> alpha 1/3; wilder(3) -> alpha 1/3 as well
		expectSeriesClose(emaSpan(src, 5, 2), ema(src, 1 / 3, 2));
		expectSeriesClose(wilder(src, 3), ema(src, 1 / 3, 3));
	});

	it('percent rank, skew, kurtosis, autocorrelation follow their definitions', () => {
		const src = CLEAN;
		const rank = rollingPercentRank(src, 10);
		for (const i of [10, 50, 300, 599]) {
			let below = 0;
			for (let j = i - 10; j < i; j++) if (src[j] < src[i]) below++;
			expect(rank[i]).toBeCloseTo((100 * below) / 10, 12);
		}
		expect(rank.slice(0, 10).every(Number.isNaN)).toBe(true);

		const w = 30;
		const skew = rollingSkew(src, w);
		const kurt = rollingKurtosis(src, w);
		const i = 400;
		const xs = Array.from(src.subarray(i - w + 1, i + 1));
		const mean = sum(xs) / w;
		const m2 = sum(xs.map((x) => (x - mean) ** 2)) / w;
		const m3 = sum(xs.map((x) => (x - mean) ** 3)) / w;
		const m4 = sum(xs.map((x) => (x - mean) ** 4)) / w;
		expect(skew[i]).toBeCloseTo((Math.sqrt(w * (w - 1)) / (w - 2)) * (m3 / m2 ** 1.5), 10);
		expect(kurt[i]).toBeCloseTo(
			(((w * w - 1) * m4) / m2 ** 2 - 3 * (w - 1) ** 2) / ((w - 2) * (w - 3)),
			10
		);

		const ac = rollingAutocorrelation(src, 25, 2);
		const k = 300;
		const a = Array.from(src.subarray(k - 24, k + 1));
		const b = Array.from(src.subarray(k - 26, k - 1));
		const ma = sum(a) / 25;
		const mb = sum(b) / 25;
		const cov = sum(a.map((x, j) => (x - ma) * (b[j] - mb)));
		expect(ac[k]).toBeCloseTo(
			cov / Math.sqrt(sum(a.map((x) => (x - ma) ** 2)) * sum(b.map((x) => (x - mb) ** 2))),
			10
		);
	});

	it('rolling regression recovers an exact line and matches least squares', () => {
		const line = Float64Array.from({ length: 50 }, (_, i) => 3 + 0.5 * i);
		const fit = rollingRegression(line, 10);
		expect(fit.slope[9]).toBeCloseTo(0.5, 12);
		expect(fit.value[49]).toBeCloseTo(3 + 0.5 * 49, 10);
		expect(fit.r2[49]).toBeCloseTo(1, 10);

		const w = 15;
		const i = 200;
		const ys = Array.from(CLEAN.subarray(i - w + 1, i + 1));
		const xbar = (w - 1) / 2;
		const ybar = sum(ys) / w;
		const sxy = sum(ys.map((y, x) => (x - xbar) * (y - ybar)));
		const sxx = sum(ys.map((_, x) => (x - xbar) ** 2));
		const reg = rollingRegression(CLEAN, w);
		expect(reg.slope[i]).toBeCloseTo(sxy / sxx, 10);
		expect(reg.value[i]).toBeCloseTo(ybar + (sxy / sxx) * xbar, 9);
	});

	it('constant windows give zero slope and undefined R²', () => {
		const flat = new Float64Array(40).fill(7.25);
		const fit = rollingRegression(flat, 10);
		expect(Math.abs(fit.slope[20])).toBeLessThan(1e-12);
		expect(fit.r2[20]).toBeNaN();
	});
});

describe('non-finite inputs never poison running windows', () => {
	it('recovers exactly once the window is clean again', () => {
		const src = new Float64Array([1, 2, NaN, 4, 5, 6, 7, 8]);
		expect(Array.from(rollingMean(src, 2))).toEqual([NaN, 1.5, NaN, NaN, 4.5, 5.5, 6.5, 7.5]);
		expect(Array.from(rollingSum(src, 3))).toEqual([NaN, NaN, NaN, NaN, NaN, 15, 18, 21]);
	});

	it('treats Infinity like NaN and keeps later results identical to a clean recomputation', () => {
		const dirty = noisy(300, 7, [50, 51, 120]);
		const cleanTail = dirty.slice(125);
		for (const fn of [
			(s: Float64Array) => rollingSum(s, 10),
			(s: Float64Array) => rollingStd(s, 10, 1),
			(s: Float64Array) => rollingMax(s, 10),
			(s: Float64Array) => wma(s, 10),
			(s: Float64Array) => rollingRegression(s, 10).slope
		]) {
			const full = fn(dirty);
			const tail = fn(cleanTail);
			for (let i = 10; i < tail.length; i++) expect(close(full[125 + i], tail[i], 1e-9)).toBe(true);
			expect(Number.isNaN(full[50])).toBe(true);
			expect(Number.isNaN(full[59])).toBe(true);
			expect(Number.isFinite(full[61])).toBe(true);
		}
	});

	it('ema skips a hole (NaN at that bar) and keeps its state', () => {
		const out = ema(new Float64Array([1, 2, NaN, 3]), 0.5, 1);
		expect(out[2]).toBeNaN();
		expect(out[3]).toBeCloseTo(0.5 * 1.5 + 0.5 * 3 - 0, 12);
	});

	it('a spike leaving the window does not leave rounding error behind', () => {
		const src = new Float64Array(20).fill(1);
		src[0] = 1e13;
		expect(rollingSum(src, 3)[19]).toBe(3);
		expect(rollingSum(src, 3)[3]).toBe(3);
		const std = rollingStd(src, 4, 0);
		expect(std[10]).toBeLessThan(1e-9);
		const varying = Float64Array.from({ length: 30 }, (_, i) => (i === 0 ? 1e9 : (i % 3) + 1));
		expectSeriesClose(
			rollingVariance(varying, 5, 0),
			brute(varying, 5, (x) => variance(x, 0)),
			1e-9
		);
	});

	it('an all-zero window sums to exactly zero after non-zero values leave', () => {
		const src = new Float64Array([0.1, 0.2, 0.3, 0, 0, 0, 0]);
		expect(rollingSum(src, 3)[6]).toBe(0);
	});
});

describe('edge cases', () => {
	const empty = new Float64Array(0);
	const short = new Float64Array([1, 2, 3]);

	it('empty input returns empty arrays', () => {
		for (const out of [
			rollingSum(empty, 3),
			rollingMean(empty, 3),
			rollingStd(empty, 3),
			rollingMax(empty, 3),
			rollingMin(empty, 3),
			ema(empty, 0.5),
			wma(empty, 3),
			shift(empty, 1),
			rsi(empty, 14),
			trueRange(empty, empty, empty),
			rollingPercentRank(empty, 5),
			rollingRegression(empty, 5).slope,
			finiteRun(empty)
		]) {
			expect(out).toHaveLength(0);
		}
	});

	it('input shorter than the window is all NaN and keeps its length', () => {
		for (const out of [
			rollingSum(short, 4),
			rollingMean(short, 4),
			rollingStd(short, 4),
			rollingMax(short, 4),
			rollingArgMin(short, 4),
			wma(short, 4),
			rollingPercentRank(short, 4),
			rollingSkew(short, 4),
			rollingKurtosis(short, 4),
			rollingRegression(short, 4).value,
			rollingAutocorrelation(short, 3, 1)
		]) {
			expect(out).toHaveLength(3);
			expect(out.every(Number.isNaN)).toBe(true);
		}
	});

	it('window equal to the length yields exactly one value', () => {
		const out = rollingMean(short, 3);
		expect(Array.from(out)).toEqual([NaN, NaN, 2]);
	});
});

describe('hand-verified small cases', () => {
	it('SMA', () => {
		expect(Array.from(rollingMean(new Float64Array([1, 2, 3, 4, 5]), 3))).toEqual([
			NaN,
			NaN,
			2,
			3,
			4
		]);
	});

	it('EMA (span 3, alpha 0.5, seeded with the first value)', () => {
		const out = emaSpan(new Float64Array([1, 2, 3, 4]), 3);
		expect(out[0]).toBeNaN();
		expect(out[1]).toBeNaN();
		expect(out[2]).toBeCloseTo(2.25, 12); // 1 -> 1.5 -> 2.25
		expect(out[3]).toBeCloseTo(3.125, 12);
	});

	it('WMA', () => {
		// (1*1 + 2*2 + 3*3) / 6 = 14/6
		const out = wma(new Float64Array([1, 2, 3, 4]), 3);
		expect(out[2]).toBeCloseTo(14 / 6, 12);
		expect(out[3]).toBeCloseTo((2 + 6 + 12) / 6, 12);
	});

	it('RSI extremes follow the backend: gains -> 100, losses -> 0, flat -> 50', () => {
		const up = Float64Array.from({ length: 30 }, (_, i) => 100 + i);
		const down = Float64Array.from({ length: 30 }, (_, i) => 100 - i);
		const flat = new Float64Array(30).fill(100);
		expect(rsi(up, 14)[29]).toBe(100);
		expect(rsi(down, 14)[29]).toBe(0);
		expect(rsi(flat, 14)[29]).toBe(50);
		expect(rsi(up, 14)[13]).toBeNaN();
		expect(rsi(up, 14)[14]).toBe(100);
	});

	it('true range covers gaps against the previous close', () => {
		const high = new Float64Array([10, 13, 11]);
		const low = new Float64Array([9, 12, 8]);
		const close = new Float64Array([9.5, 12.5, 9]);
		// bar0: 1 (no previous close); bar1: gap up, |13-9.5| = 3.5; bar2: |8-12.5| = 4.5
		expect(Array.from(trueRange(high, low, close))).toEqual([1, 3.5, 4.5]);
	});
});
