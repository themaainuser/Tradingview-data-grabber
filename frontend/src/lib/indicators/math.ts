/**
 * Shared O(n) numeric primitives.
 *
 * Conventions
 * - Every function returns a fresh `Float64Array` of the input length; warm-up is `NaN`.
 * - Windows are strict: a rolling value needs `w` consecutive finite inputs. A non-finite input
 *   resets the running state, so results recover as soon as the window is clean again.
 * - Window arguments must be positive integers (definitions guarantee this via `resolveParams`).
 * - Running sums are re-synchronised from the raw window every `RESYNC` steps to bound drift.
 */

export type Series = Float64Array;

const RESYNC = 256;

export const nanArray = (n: number): Series => new Float64Array(n).fill(NaN);

/** `run[i]` = number of consecutive finite values ending at `i` (0 when `src[i]` is not finite). */
export function finiteRun(src: Series): Int32Array {
	const run = new Int32Array(src.length);
	let count = 0;
	for (let i = 0; i < src.length; i++) {
		count = Number.isFinite(src[i]) ? count + 1 : 0;
		run[i] = count;
	}
	return run;
}

// ---------------------------------------------------------------------------------------------
// Element-wise helpers (NaN propagates; division by zero yields NaN)
// ---------------------------------------------------------------------------------------------

export function map(src: Series, fn: (x: number) => number): Series {
	const out = new Float64Array(src.length);
	for (let i = 0; i < src.length; i++) out[i] = fn(src[i]);
	return out;
}

export function zip(a: Series, b: Series, fn: (x: number, y: number) => number): Series {
	const out = new Float64Array(a.length);
	for (let i = 0; i < a.length; i++) out[i] = fn(a[i], b[i]);
	return out;
}

export const add = (a: Series, b: Series): Series => zip(a, b, (x, y) => x + y);
export const sub = (a: Series, b: Series): Series => zip(a, b, (x, y) => x - y);
export const mul = (a: Series, b: Series): Series => zip(a, b, (x, y) => x * y);
export const div = (a: Series, b: Series): Series => zip(a, b, (x, y) => (y === 0 ? NaN : x / y));
export const scale = (a: Series, k: number): Series => map(a, (x) => x * k);
export const offset = (a: Series, k: number): Series => map(a, (x) => x + k);
export const abs = (a: Series): Series => map(a, Math.abs);
/** `100 * (a / b - 1)`. */
export const pctDiff = (a: Series, b: Series): Series =>
	zip(a, b, (x, y) => (y === 0 ? NaN : 100 * (x / y - 1)));

export const clamp = (a: Series, lo: number, hi: number): Series =>
	map(a, (x) => (x < lo ? lo : x > hi ? hi : x));

/**
 * True when `spread` is negligible relative to `level` (running-sum noise on a flat window), so
 * ratios such as z-scores are reported as undefined instead of amplifying rounding error.
 */
export const isDegenerate = (spread: number, level: number): boolean =>
	!(spread > 1e-12 * Math.abs(level));

/** Standard score `(x - mean) / sd`; NaN when `sd` is negligible relative to `mean`. */
export function zScore(x: Series, mean: Series, sd: Series): Series {
	const out = nanArray(x.length);
	for (let i = 0; i < out.length; i++) {
		if (!isDegenerate(sd[i], mean[i])) out[i] = (x[i] - mean[i]) / sd[i];
	}
	return out;
}

/** `out[i] = src[i - k]`. */
export function shift(src: Series, k: number): Series {
	const out = nanArray(src.length);
	for (let i = k; i < src.length; i++) out[i] = src[i - k];
	return out;
}

/** `out[i] = src[i] - src[i - k]`. */
export function diff(src: Series, k = 1): Series {
	const out = nanArray(src.length);
	for (let i = k; i < src.length; i++) out[i] = src[i] - src[i - k];
	return out;
}

/** Rate of change in percent: `100 * (src[i] / src[i - k] - 1)`. */
export const rateOfChange = (src: Series, k: number): Series => pctDiff(src, shift(src, k));

/** Simple return `src[i] / src[i - k] - 1` (a ratio, not percent). */
export function pctChange(src: Series, k = 1): Series {
	const out = nanArray(src.length);
	for (let i = k; i < src.length; i++) {
		const prev = src[i - k];
		out[i] = prev === 0 ? NaN : src[i] / prev - 1;
	}
	return out;
}

/** `ln(src[i] / src[i - k])`; NaN unless both prices are positive. */
export function logChange(src: Series, k = 1): Series {
	const out = nanArray(src.length);
	for (let i = k; i < src.length; i++) {
		const ratio = src[i] / src[i - k];
		out[i] = ratio > 0 ? Math.log(ratio) : NaN;
	}
	return out;
}

// ---------------------------------------------------------------------------------------------
// Rolling window statistics
// ---------------------------------------------------------------------------------------------

function sumRange(src: Series, from: number, to: number): number {
	let s = 0;
	for (let i = from; i <= to; i++) s += src[i];
	return s;
}

export function rollingSum(src: Series, w: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 1) || n < w) return out;
	let sum = 0;
	let run = 0;
	let nonzero = 0;
	let stale = false;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) {
			sum = 0;
			run = 0;
			nonzero = 0;
			stale = false;
			continue;
		}
		run++;
		sum += x;
		if (x !== 0) nonzero++;
		if (run > w) {
			const old = src[i - w];
			sum -= old;
			if (old !== 0) nonzero--;
			// A spike leaving the window would leave its rounding error behind: rebuild the sum.
			if (Math.abs(sum) < 1e-9 * Math.abs(old)) stale = true;
		}
		if (run < w) continue;
		// An all-zero window must sum to exactly 0 (callers branch on zero denominators).
		if (nonzero === 0) {
			sum = 0;
			stale = false;
		} else if (stale || run % RESYNC === 0) {
			sum = sumRange(src, i - w + 1, i);
			stale = false;
		}
		out[i] = sum;
	}
	return out;
}

export function rollingMean(src: Series, w: number): Series {
	const out = rollingSum(src, w);
	for (let i = 0; i < out.length; i++) out[i] /= w;
	return out;
}

/** Rolling variance via Welford add/remove updates (stable when mean >> spread). */
export function rollingVariance(src: Series, w: number, ddof = 0): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 1) || w <= ddof || n < w) return out;
	let count = 0;
	let mean = 0;
	let m2 = 0;
	let run = 0;
	let stale = false;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) {
			count = 0;
			mean = 0;
			m2 = 0;
			run = 0;
			stale = false;
			continue;
		}
		run++;
		if (count === w) {
			const old = src[i - w];
			const before = m2;
			count--;
			if (count === 0) {
				mean = 0;
				m2 = 0;
			} else {
				const d = old - mean;
				mean -= d / count;
				m2 -= d * (old - mean);
				// An outlier leaving the window cancels almost all of M2: rebuild from the raw window.
				if (m2 < 1e-6 * before) stale = true;
			}
		}
		count++;
		const d = x - mean;
		mean += d / count;
		m2 += d * (x - mean);
		if (count < w) continue;
		if (stale || run % RESYNC === 0) {
			mean = sumRange(src, i - w + 1, i) / w;
			m2 = 0;
			for (let j = i - w + 1; j <= i; j++) m2 += (src[j] - mean) * (src[j] - mean);
			stale = false;
		}
		out[i] = Math.max(m2, 0) / (w - ddof);
	}
	return out;
}

/** Rolling standard deviation; `ddof = 0` is the population estimate (as in the backend). */
export function rollingStd(src: Series, w: number, ddof = 0): Series {
	const out = rollingVariance(src, w, ddof);
	for (let i = 0; i < out.length; i++) out[i] = Math.sqrt(out[i]);
	return out;
}

/** Monotonic-deque sliding extreme; the most recent index wins ties. */
function slideExtreme(
	src: Series,
	w: number,
	isMax: boolean,
	values: Series | null,
	indexes: Series | null
): void {
	const n = src.length;
	if (!(w >= 1) || n < w) return;
	const queue = new Int32Array(n);
	let head = 0;
	let tail = 0;
	let run = 0;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) {
			head = 0;
			tail = 0;
			run = 0;
			continue;
		}
		run++;
		while (tail > head && (isMax ? src[queue[tail - 1]] <= x : src[queue[tail - 1]] >= x)) tail--;
		queue[tail++] = i;
		while (queue[head] <= i - w) head++;
		if (run < w) continue;
		const j = queue[head];
		if (values) values[i] = src[j];
		if (indexes) indexes[i] = j;
	}
}

export function rollingMax(src: Series, w: number): Series {
	const out = nanArray(src.length);
	slideExtreme(src, w, true, out, null);
	return out;
}

export function rollingMin(src: Series, w: number): Series {
	const out = nanArray(src.length);
	slideExtreme(src, w, false, out, null);
	return out;
}

/** Absolute bar index of the window maximum. */
export function rollingArgMax(src: Series, w: number): Series {
	const out = nanArray(src.length);
	slideExtreme(src, w, true, null, out);
	return out;
}

/** Absolute bar index of the window minimum. */
export function rollingArgMin(src: Series, w: number): Series {
	const out = nanArray(src.length);
	slideExtreme(src, w, false, null, out);
	return out;
}

// ---------------------------------------------------------------------------------------------
// Exponential and weighted averages
// ---------------------------------------------------------------------------------------------

/**
 * Exponential average matching pandas `ewm(alpha, adjust=False, min_periods)`: seeded with the
 * first finite value, output starts once `minPeriods` finite observations were seen. A
 * non-finite input yields NaN at that bar and leaves the state untouched.
 */
export function ema(src: Series, alpha: number, minPeriods = 1): Series {
	const n = src.length;
	const out = nanArray(n);
	const decay = 1 - alpha;
	let state = 0;
	let obs = 0;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) continue;
		state = obs === 0 ? x : decay * state + alpha * x;
		obs++;
		if (obs >= minPeriods) out[i] = state;
	}
	return out;
}

/** EMA with `alpha = 2 / (span + 1)`; `minPeriods` defaults to `span`. */
export const emaSpan = (src: Series, span: number, minPeriods = span): Series =>
	ema(src, 2 / (span + 1), minPeriods);

/**
 * Wilder smoothing (`alpha = 1 / period`), seeded with the first observation like the backend's
 * pandas `ewm(alpha=1/period, adjust=False, min_periods=period)`; it converges to the classic
 * SMA-seeded form.
 */
export const wilder = (src: Series, period: number): Series => ema(src, 1 / period, period);

/** Linearly weighted moving average (newest bar weight `w`, oldest 1), O(n). */
export function wma(src: Series, w: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 1) || n < w) return out;
	const denom = (w * (w + 1)) / 2;
	let count = 0;
	let sum = 0;
	let weighted = 0;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) {
			count = 0;
			sum = 0;
			weighted = 0;
			continue;
		}
		if (count < w) {
			count++;
			sum += x;
			weighted += count * x;
		} else {
			const old = src[i - w];
			weighted += w * x - sum;
			sum += x - old;
			// Re-derive from the raw window periodically (or after a spike leaves) to bound drift.
			if (i % RESYNC === 0 || Math.abs(sum) < 1e-9 * Math.abs(old)) {
				sum = 0;
				weighted = 0;
				for (let k = 0; k < w; k++) {
					const v = src[i - w + 1 + k];
					sum += v;
					weighted += (k + 1) * v;
				}
			}
		}
		if (count >= w) out[i] = weighted / denom;
	}
	return out;
}

/** 4-bar symmetric weighted average (1, 2, 2, 1) / 6, as used by the Relative Vigor Index. */
export function swma4(src: Series): Series {
	const out = nanArray(src.length);
	for (let i = 3; i < src.length; i++) {
		out[i] = (src[i] + 2 * src[i - 1] + 2 * src[i - 2] + src[i - 3]) / 6;
	}
	return out;
}

// ---------------------------------------------------------------------------------------------
// Ranges and price helpers
// ---------------------------------------------------------------------------------------------

/**
 * True range. Bar 0 has no previous close and uses `high - low` (pandas `max(skipna=True)` in
 * the backend). A non-finite previous close makes the next bar NaN.
 */
export function trueRange(high: Series, low: Series, close: Series): Series {
	const n = high.length;
	const out = nanArray(n);
	if (n === 0) return out;
	out[0] = high[0] - low[0];
	for (let i = 1; i < n; i++) {
		const pc = close[i - 1];
		out[i] = Math.max(high[i] - low[i], Math.abs(high[i] - pc), Math.abs(low[i] - pc));
	}
	return out;
}

/** Wilder-smoothed true range (`ATR`), seeded like the backend RSI (see `wilder`). */
export const atrWilder = (high: Series, low: Series, close: Series, period: number): Series =>
	wilder(trueRange(high, low, close), period);

/** ATR as a simple rolling mean of true range, matching the backend's `atr_14`. */
export const atrSma = (high: Series, low: Series, close: Series, period: number): Series =>
	rollingMean(trueRange(high, low, close), period);

/** Close-location value in [-1, 1]; a zero-range bar is 0 (TA-Lib convention). */
export function closeLocationValue(high: Series, low: Series, close: Series): Series {
	const n = high.length;
	const out = new Float64Array(n);
	for (let i = 0; i < n; i++) {
		const range = high[i] - low[i];
		out[i] = range === 0 ? 0 : (2 * close[i] - high[i] - low[i]) / range;
	}
	return out;
}

// ---------------------------------------------------------------------------------------------
// Oscillator building blocks
// ---------------------------------------------------------------------------------------------

/**
 * RSI from a series of changes using Wilder smoothing as in the backend: `100 - 100 / (1 + rs)`,
 * with zero average loss -> 100 (or 50 when there are no gains either) and zero gain -> 0.
 */
export function rsiFromChanges(changes: Series, period: number): Series {
	const n = changes.length;
	const gains = nanArray(n);
	const losses = nanArray(n);
	for (let i = 0; i < n; i++) {
		const d = changes[i];
		if (Number.isNaN(d)) continue;
		gains[i] = d > 0 ? d : 0;
		losses[i] = d < 0 ? -d : 0;
	}
	const avgGain = wilder(gains, period);
	const avgLoss = wilder(losses, period);
	const out = nanArray(n);
	for (let i = 0; i < n; i++) {
		const g = avgGain[i];
		const l = avgLoss[i];
		if (Number.isNaN(g) || Number.isNaN(l)) continue;
		if (l === 0) out[i] = g > 0 ? 100 : 50;
		else if (g === 0) out[i] = 0;
		else out[i] = 100 - 100 / (1 + g / l);
	}
	return out;
}

export const rsi = (src: Series, period: number): Series => rsiFromChanges(diff(src, 1), period);

/** Slow/fast stochastic position `100 * (x - min) / (max - min)` over a rolling window. */
export function stochasticPosition(value: Series, highest: Series, lowest: Series): Series {
	return zip3(value, highest, lowest, (x, hi, lo) =>
		hi === lo ? NaN : (100 * (x - lo)) / (hi - lo)
	);
}

export function zip3(
	a: Series,
	b: Series,
	c: Series,
	fn: (x: number, y: number, z: number) => number
): Series {
	const out = new Float64Array(a.length);
	for (let i = 0; i < a.length; i++) out[i] = fn(a[i], b[i], c[i]);
	return out;
}

// ---------------------------------------------------------------------------------------------
// Bounded-window statistics (O(n * w); defaults stay <= 100)
// ---------------------------------------------------------------------------------------------

/** Percent of the previous `w` values strictly below the current one. */
export function rollingPercentRank(src: Series, w: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 1) || n <= w) return out;
	const run = finiteRun(src);
	for (let i = w; i < n; i++) {
		if (run[i] < w + 1) continue;
		const x = src[i];
		let below = 0;
		for (let j = i - w; j < i; j++) if (src[j] < x) below++;
		out[i] = (100 * below) / w;
	}
	return out;
}

/** Central moments of a finite window: returns `[mean, m2, m3, m4]` (population, divided by w). */
function centralMoments(src: Series, from: number, w: number): [number, number, number, number] {
	let mean = 0;
	for (let j = from; j < from + w; j++) mean += src[j];
	mean /= w;
	let m2 = 0;
	let m3 = 0;
	let m4 = 0;
	for (let j = from; j < from + w; j++) {
		const d = src[j] - mean;
		const d2 = d * d;
		m2 += d2;
		m3 += d2 * d;
		m4 += d2 * d2;
	}
	return [mean, m2 / w, m3 / w, m4 / w];
}

/** Bias-corrected sample skewness (pandas `rolling.skew`); needs `w >= 3`. */
export function rollingSkew(src: Series, w: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 3) || n < w) return out;
	const run = finiteRun(src);
	const k = Math.sqrt(w * (w - 1)) / (w - 2);
	for (let i = w - 1; i < n; i++) {
		if (run[i] < w) continue;
		const [mean, m2, m3] = centralMoments(src, i - w + 1, w);
		if (!(m2 > 1e-24 * mean * mean)) continue;
		out[i] = (k * m3) / Math.pow(m2, 1.5);
	}
	return out;
}

/** Bias-corrected excess kurtosis (pandas `rolling.kurt`); needs `w >= 4`. */
export function rollingKurtosis(src: Series, w: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 4) || n < w) return out;
	const run = finiteRun(src);
	for (let i = w - 1; i < n; i++) {
		if (run[i] < w) continue;
		const [mean, m2, , m4] = centralMoments(src, i - w + 1, w);
		if (!(m2 > 1e-24 * mean * mean)) continue;
		out[i] = ((w * w - 1) * (m4 / (m2 * m2)) - 3 * (w - 1) * (w - 1)) / ((w - 2) * (w - 3));
	}
	return out;
}

/** Rolling Pearson correlation between `src[j]` and `src[j - lag]` over `w` pairs. */
export function rollingAutocorrelation(src: Series, w: number, lag: number): Series {
	const n = src.length;
	const out = nanArray(n);
	if (!(w >= 2) || !(lag >= 1) || n < w + lag) return out;
	const run = finiteRun(src);
	for (let i = w + lag - 1; i < n; i++) {
		if (run[i] < w + lag) continue;
		let mx = 0;
		let my = 0;
		for (let j = i - w + 1; j <= i; j++) {
			mx += src[j];
			my += src[j - lag];
		}
		mx /= w;
		my /= w;
		let sxy = 0;
		let sxx = 0;
		let syy = 0;
		for (let j = i - w + 1; j <= i; j++) {
			const dx = src[j] - mx;
			const dy = src[j - lag] - my;
			sxy += dx * dy;
			sxx += dx * dx;
			syy += dy * dy;
		}
		const denom = sxx * syy;
		if (denom > 0) out[i] = Math.min(1, Math.max(-1, sxy / Math.sqrt(denom)));
	}
	return out;
}

export interface Regression {
	slope: Series;
	/** Fitted value at the last bar of each window (the "linear regression" value). */
	value: Series;
	r2: Series;
}

/**
 * Rolling least-squares line over the last `w` bars against x = 0..w-1, in O(n). Sums are kept
 * relative to a reference price (`ref`) to avoid cancellation on trending series.
 */
export function rollingRegression(src: Series, w: number): Regression {
	const n = src.length;
	const slope = nanArray(n);
	const value = nanArray(n);
	const r2 = nanArray(n);
	if (!(w >= 2) || n < w) return { slope, value, r2 };
	const xbar = (w - 1) / 2;
	const sxx = (w * (w * w - 1)) / 12;
	let run = 0;
	let ref = 0;
	let sy = 0;
	let sxy = 0;
	let syy = 0;
	for (let i = 0; i < n; i++) {
		const x = src[i];
		if (!Number.isFinite(x)) {
			run = 0;
			continue;
		}
		run++;
		if (run === 1) {
			ref = x;
			sy = 0;
			sxy = 0;
			syy = 0;
		}
		const y = x - ref;
		if (run <= w) {
			sxy += (run - 1) * y;
			sy += y;
			syy += y * y;
		} else {
			const old = src[i - w] - ref;
			sxy += (w - 1) * y - (sy - old);
			sy += y - old;
			syy += y * y - old * old;
		}
		if (run < w) continue;
		if (run % RESYNC === 0) {
			ref = src[i - w + 1];
			sy = 0;
			sxy = 0;
			syy = 0;
			for (let k = 0; k < w; k++) {
				const yk = src[i - w + 1 + k] - ref;
				sy += yk;
				sxy += k * yk;
				syy += yk * yk;
			}
		}
		const cov = sxy - xbar * sy;
		const b = cov / sxx;
		slope[i] = b;
		value[i] = ref + sy / w + b * xbar;
		const spread = syy - (sy * sy) / w;
		if (spread > 1e-12 * syy) r2[i] = Math.min(1, Math.max(0, (cov * cov) / (sxx * spread)));
	}
	return { slope, value, r2 };
}
