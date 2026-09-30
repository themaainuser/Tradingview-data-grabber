/**
 * Pure helpers behind the SVG chart components: domains, decimation, path building, time ticks,
 * label collision handling and the brand colour ramps used by the heatmap.
 */
import { MISSING } from '$lib/format';

export type Maybe = number | null | undefined;

const finite = (v: Maybe): v is number => typeof v === 'number' && Number.isFinite(v);

/** Min/max ignoring null, undefined, NaN and +-Infinity; null when nothing is usable. */
export function extent(values: Iterable<Maybe>): [number, number] | null {
	let min = Infinity;
	let max = -Infinity;
	for (const v of values) {
		if (!finite(v)) continue;
		if (v < min) min = v;
		if (v > max) max = v;
	}
	return min <= max ? [min, max] : null;
}

export function mergeExtents(list: readonly ([number, number] | null)[]): [number, number] | null {
	let out: [number, number] | null = null;
	for (const e of list) {
		if (!e) continue;
		out = out ? [Math.min(out[0], e[0]), Math.max(out[1], e[1])] : [e[0], e[1]];
	}
	return out;
}

/** Widens a domain by `ratio` of its span on both sides; a flat domain gets a visible span. */
export function padDomain(min: number, max: number, ratio = 0.06): [number, number] {
	if (max < min) [min, max] = [max, min];
	if (min === max) {
		const spread = Math.abs(min) * 0.05 || 1;
		return [min - spread, max + spread];
	}
	const pad = (max - min) * ratio;
	return [min - pad, max + pad];
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
export const clamp01 = (v: number) => (v !== v ? 0 : clamp(v, 0, 1));

/** Index of the entry in ascending `times` nearest to `t` (ties go to the earlier one); -1 when empty. */
export function bisectTime(times: ArrayLike<number>, t: number): number {
	const n = times.length;
	if (n === 0) return -1;
	let lo = 0;
	let hi = n - 1;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if (times[mid] < t) lo = mid + 1;
		else hi = mid;
	}
	if (lo > 0 && t - times[lo - 1] <= times[lo] - t) return lo - 1;
	return lo;
}

/**
 * Reduces a series to the indices worth drawing at `width` pixels: per pixel column the first,
 * minimum, maximum and last point (M4), so spikes and troughs survive. Gaps (null/NaN) are kept
 * as a single index so path builders can still break the line there.
 */
export function columnDecimate(
	times: ArrayLike<number>,
	values: ArrayLike<Maybe>,
	width: number
): number[] {
	const n = Math.min(times.length, values.length);
	const out: number[] = [];
	if (n === 0) return out;
	if (n <= width * 2 || width < 1) {
		for (let i = 0; i < n; i++) out.push(i);
		return out;
	}
	const t0 = times[0];
	const span = times[n - 1] - t0;
	const column = (i: number) =>
		span > 0 ? Math.floor(((times[i] - t0) / span) * width) : Math.floor((i / n) * width);

	let col = -1;
	let first = -1;
	let last = -1;
	let lo = -1;
	let hi = -1;
	let afterGap = false;
	const flush = () => {
		if (first < 0) return;
		const picks = [first, lo, hi, last].sort((a, b) => a - b);
		for (let k = 0; k < picks.length; k++)
			if (k === 0 || picks[k] !== picks[k - 1]) out.push(picks[k]);
		first = last = lo = hi = -1;
	};
	for (let i = 0; i < n; i++) {
		const v = values[i];
		if (!finite(v)) {
			flush();
			col = -1;
			if (!afterGap) out.push(i);
			afterGap = true;
			continue;
		}
		afterGap = false;
		const c = column(i);
		if (c !== col) {
			flush();
			col = c;
			first = last = lo = hi = i;
			continue;
		}
		last = i;
		if (v < (values[lo] as number)) lo = i;
		if (v > (values[hi] as number)) hi = i;
	}
	flush();
	return out;
}

/** Splits draw-order indices into runs of consecutive finite values. */
export function segments(indices: readonly number[], values: ArrayLike<Maybe>): number[][] {
	const runs: number[][] = [];
	let run: number[] | null = null;
	for (const i of indices) {
		if (!finite(values[i])) {
			run = null;
			continue;
		}
		if (!run) runs.push((run = []));
		run.push(i);
	}
	return runs;
}

const px = (n: number) => String(Math.round(n * 100) / 100);

/** SVG path for a line; gaps start a new subpath and an isolated point becomes a zero-length dot. */
export function linePath(
	indices: readonly number[],
	values: ArrayLike<Maybe>,
	x: (index: number) => number,
	y: (value: number) => number
): string {
	const parts: string[] = [];
	for (const run of segments(indices, values)) {
		for (let k = 0; k < run.length; k++) {
			const i = run[k];
			parts.push(`${k === 0 ? 'M' : 'L'}${px(x(i))} ${px(y(values[i] as number))}`);
		}
		if (run.length === 1) parts.push('h0');
	}
	return parts.join('');
}

/** SVG path for a filled area; every run of values closes down to `baseY` on its own. */
export function areaPath(
	indices: readonly number[],
	values: ArrayLike<Maybe>,
	x: (index: number) => number,
	y: (value: number) => number,
	baseY: number
): string {
	const parts: string[] = [];
	for (const run of segments(indices, values)) {
		if (run.length < 2) continue;
		const base = px(baseY);
		parts.push(`M${px(x(run[0]))} ${base}`);
		for (const i of run) parts.push(`L${px(x(i))} ${px(y(values[i] as number))}`);
		parts.push(`L${px(x(run[run.length - 1]))} ${base}Z`);
	}
	return parts.join('');
}

const DAY = 86_400;
const FIXED_STEPS = [
	60,
	300,
	900,
	1800,
	3600,
	3 * 3600,
	6 * 3600,
	12 * 3600,
	DAY,
	2 * DAY,
	7 * DAY,
	14 * DAY
];
/** 1970-01-05 was a Monday, so weekly steps land on Mondays. */
const MONDAY_OFFSET = 4 * DAY;

/** Axis labels carry a time of day when the visible span is shorter than three days. */
export const showsTimeOfDay = (t0: number, t1: number) => t1 - t0 < 3 * DAY;

/** Calendar-aligned (UTC) tick times inside [t0, t1], at most about `count` of them. */
export function timeTicks(t0: number, t1: number, count: number): number[] {
	if (!Number.isFinite(t0) || !Number.isFinite(t1)) return [];
	if (t1 <= t0) return [t0];
	const span = t1 - t0;
	const target = Math.max(1, Math.floor(count));
	const minStep = showsTimeOfDay(t0, t1) ? 60 : DAY;

	for (const step of FIXED_STEPS) {
		if (step < minStep || span / step > target) continue;
		const offset = step % (7 * DAY) === 0 ? MONDAY_OFFSET : 0;
		const ticks: number[] = [];
		for (let t = Math.ceil((t0 - offset) / step) * step + offset; t <= t1; t += step) ticks.push(t);
		return ticks;
	}

	const startYear = new Date(t0 * 1000).getUTCFullYear();
	const startMonth = new Date(t0 * 1000).getUTCMonth();
	for (const months of [1, 3, 6, 12, 24, 60, 120, 240, 600, 1200]) {
		if (span / (months * 30.44 * DAY) > target && months < 1200) continue;
		const ticks: number[] = [];
		let total = Math.ceil((startYear * 12 + startMonth) / months) * months;
		for (;;) {
			const t = Date.UTC(Math.floor(total / 12), total % 12, 1) / 1000;
			if (t > t1) break;
			if (t >= t0) ticks.push(t);
			total += months;
		}
		return ticks;
	}
	return [];
}

const numberFormat = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 6 });

/** Default value formatter for tooltips: up to six significant digits with thousands separators. */
export const formatNumber = (v: Maybe): string => (finite(v) ? numberFormat.format(v) : MISSING);

/**
 * Moves a cursor index from a key press; null for keys that are not navigation. On the x axis
 * the arrows are left/right and PageDown advances; on the y axis ArrowUp/PageUp go to a higher
 * index (a higher price). A missing cursor starts from the end the key moves away from.
 */
export function stepIndex(
	key: string,
	current: number | null,
	count: number,
	options: { axis: 'x' | 'y'; page?: number }
): number | null {
	if (count <= 0) return null;
	const size = Math.max(1, options.page ?? Math.round(count / 10));
	const horizontal = options.axis === 'x';
	const deltas: Record<string, number> = horizontal
		? { ArrowRight: 1, ArrowLeft: -1, PageDown: size, PageUp: -size }
		: { ArrowUp: 1, ArrowDown: -1, PageUp: size, PageDown: -size };
	if (Object.hasOwn(deltas, key)) {
		const delta = deltas[key];
		return clamp((current ?? (delta > 0 ? -1 : count)) + delta, 0, count - 1);
	}
	if (key === 'Home') return horizontal ? 0 : count - 1;
	if (key === 'End') return horizontal ? count - 1 : 0;
	return null;
}

/** Index of the bin `[edges[i], edges[i + 1])` containing `value`, clamped to the first/last bin. */
export function binIndex(edges: ArrayLike<number>, value: number): number {
	const bins = edges.length - 1;
	if (bins < 1) return -1;
	let lo = 0;
	let hi = bins - 1;
	while (lo < hi) {
		const mid = (lo + hi + 1) >> 1;
		if (edges[mid] <= value) lo = mid;
		else hi = mid - 1;
	}
	return lo;
}

/** Spreads label centres apart by at least `gap`, keeping them inside [min, max]; keeps input order. */
export function nudgeApart(
	positions: readonly number[],
	gap: number,
	min: number,
	max: number
): number[] {
	const order = positions.map((_, i) => i).sort((a, b) => positions[a] - positions[b]);
	const p = order.map((i) => clamp(positions[i], min, max));
	for (let k = 1; k < p.length; k++) p[k] = Math.max(p[k], p[k - 1] + gap);
	if (p.length && p[p.length - 1] > max) {
		p[p.length - 1] = max;
		for (let k = p.length - 2; k >= 0; k--) p[k] = Math.min(p[k], p[k + 1] - gap);
	}
	const out = new Array<number>(positions.length);
	order.forEach((original, k) => (out[original] = p[k]));
	return out;
}

/** Greedy row assignment so horizontally overlapping captions stack instead of colliding. */
export function assignRows(spans: readonly { start: number; end: number }[], gap = 6): number[] {
	const order = spans.map((_, i) => i).sort((a, b) => spans[a].start - spans[b].start);
	const rowEnds: number[] = [];
	const rows = new Array<number>(spans.length);
	for (const i of order) {
		let row = rowEnds.findIndex((end) => end + gap <= spans[i].start);
		if (row < 0) row = rowEnds.length;
		rowEnds[row] = spans[i].end;
		rows[i] = row;
	}
	return rows;
}

/* ---------------------------------------------------------------------------------------- */
/* Heatmap colour ramps                                                                      */
/* ---------------------------------------------------------------------------------------- */

type Rgb = readonly [number, number, number];
interface Stop {
	token: string;
	rgb: Rgb;
}

/**
 * sRGB mirrors of the CSS tokens, needed to compute text contrast in JS. chart-math.spec.ts
 * checks every entry against layout.css, so a token change cannot silently break contrast.
 */
export const TOKEN_RGB = {
	'--surface-2': [28, 28, 28],
	'--gradient-violet': [106, 76, 245],
	'--gradient-magenta': [212, 77, 240],
	'--gradient-orange': [255, 122, 61],
	'--gradient-coral': [255, 85, 119],
	'--semantic-success': [34, 197, 94],
	'--ink': [255, 255, 255],
	'--on-primary': [0, 0, 0]
} as const satisfies Record<string, Rgb>;

const stop = (token: keyof typeof TOKEN_RGB): Stop => ({ token, rgb: TOKEN_RGB[token] });

/** The brand atmosphere gradient: charcoal into violet, magenta, orange. */
const SEQUENTIAL: readonly Stop[] = [
	stop('--surface-2'),
	stop('--gradient-violet'),
	stop('--gradient-magenta'),
	stop('--gradient-orange')
];
/** Down (coral) through a neutral midpoint to up (success). */
const DIVERGING: readonly Stop[] = [
	stop('--gradient-coral'),
	stop('--surface-2'),
	stop('--semantic-success')
];

export type HeatScale = 'sequential' | 'diverging';
const ramp = (scale: HeatScale) => (scale === 'diverging' ? DIVERGING : SEQUENTIAL);

function locate(stops: readonly Stop[], t: number): { a: Stop; b: Stop; p: number } {
	const scaled = clamp01(t) * (stops.length - 1);
	const k = Math.min(stops.length - 2, Math.floor(scaled));
	return { a: stops[k], b: stops[k + 1], p: scaled - k };
}

function mixCss(stops: readonly Stop[], t: number): string {
	const { a, b, p } = locate(stops, t);
	const pct = Math.round(p * 1000) / 10;
	return `color-mix(in oklab, var(${b.token}) ${pct}%, var(${a.token}))`;
}

/** Colour for t in [0, 1] on the atmosphere ramp, as a CSS colour built from the design tokens. */
export const sequentialColor = (t: number): string => mixCss(SEQUENTIAL, t);
/** Colour for t in [0, 1] where 0.5 is the neutral midpoint (value 0). */
export const divergingColor = (t: number): string => mixCss(DIVERGING, t);
export const heatColor = (t: number, scale: HeatScale) =>
	scale === 'diverging' ? divergingColor(t) : sequentialColor(t);

const toLinear = (c: number) => {
	const s = c / 255;
	return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};

function toOklab([r, g, b]: Rgb): [number, number, number] {
	const [lr, lg, lb] = [toLinear(r), toLinear(g), toLinear(b)];
	const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
	const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
	const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
	return [
		0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
		1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
		0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
	];
}

function oklabToLinear([L, a, b]: readonly [number, number, number]): [number, number, number] {
	const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return [
		clamp01(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
		clamp01(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
		clamp01(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)
	];
}

/** Linear-light sRGB of the colour `heatColor(t, scale)` resolves to (oklab mix, gamut clamped). */
export function heatLinearRgb(t: number, scale: HeatScale): [number, number, number] {
	const { a, b, p } = locate(ramp(scale), t);
	const [La, Aa, Ba] = toOklab(a.rgb);
	const [Lb, Ab, Bb] = toOklab(b.rgb);
	return oklabToLinear([La + (Lb - La) * p, Aa + (Ab - Aa) * p, Ba + (Bb - Ba) * p]);
}

/** WCAG relative luminance of the colour `heatColor(t, scale)` resolves to. */
export function heatLuminance(t: number, scale: HeatScale): number {
	const [r, g, b] = heatLinearRgb(t, scale);
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const luminanceOf = (rgb: Rgb) => {
	const [r, g, b] = rgb.map(toLinear);
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** WCAG contrast ratio of a text token on the cell colour at `t`. */
export function heatContrast(t: number, scale: HeatScale, ink: 'ink' | 'on-primary'): number {
	const bg = heatLuminance(t, scale);
	const fg = luminanceOf(TOKEN_RGB[ink === 'ink' ? '--ink' : '--on-primary']);
	const [hi, lo] = fg > bg ? [fg, bg] : [bg, fg];
	return (hi + 0.05) / (lo + 0.05);
}

/**
 * Text colour for a cell: white or black, whichever contrasts more. Black is `--on-primary`
 * rather than the canvas token because canvas/white peaks below 4.5:1 for mid-lightness cells
 * (about 4.46:1), whereas black/white never drops under 4.58:1.
 */
export function contrastInk(t: number, scale: HeatScale = 'sequential'): string {
	return heatContrast(t, scale, 'ink') >= heatContrast(t, scale, 'on-primary')
		? 'var(--ink)'
		: 'var(--on-primary)';
}

/** Maps a value onto [0, 1]; diverging scales keep 0 at the neutral midpoint on both sides. */
export function normalize(
	value: number,
	domain: readonly [number, number],
	scale: HeatScale
): number {
	const [lo, hi] = domain;
	if (scale === 'diverging') {
		if (value < 0) return lo < 0 ? 0.5 - 0.5 * Math.min(1, value / lo) : 0.5;
		return hi > 0 ? 0.5 + 0.5 * Math.min(1, value / hi) : 0.5;
	}
	return hi > lo ? clamp01((value - lo) / (hi - lo)) : 0.5;
}
