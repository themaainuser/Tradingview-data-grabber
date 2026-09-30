import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
	TOKEN_RGB,
	areaPath,
	assignRows,
	binIndex,
	bisectTime,
	clamp01,
	columnDecimate,
	contrastInk,
	divergingColor,
	extent,
	formatNumber,
	heatContrast,
	heatLuminance,
	linePath,
	mergeExtents,
	normalize,
	nudgeApart,
	padDomain,
	segments,
	sequentialColor,
	showsTimeOfDay,
	stepIndex,
	timeTicks
} from './chart-math';

const DAY = 86_400;
const utc = (iso: string) => Date.parse(iso) / 1000;

describe('extent / padDomain / clamp01', () => {
	it('ignores null, NaN and infinities', () => {
		expect(extent([3, null, NaN, -2, undefined, Infinity, 7])).toEqual([-2, 7]);
	});
	it('returns null when nothing is usable', () => {
		expect(extent([])).toBeNull();
		expect(extent([null, NaN])).toBeNull();
	});
	it('merges extents and skips empty ones', () => {
		expect(mergeExtents([[1, 2], null, [0, 1.5]])).toEqual([0, 2]);
		expect(mergeExtents([null])).toBeNull();
	});
	it('pads both sides by the ratio', () => {
		const [lo, hi] = padDomain(0, 100);
		expect(lo).toBeCloseTo(-6);
		expect(hi).toBeCloseTo(106);
	});
	it('gives a flat domain a real span', () => {
		const [lo, hi] = padDomain(50, 50);
		expect(hi - lo).toBeGreaterThan(0);
		expect(padDomain(0, 0)).toEqual([-1, 1]);
	});
	it('clamps to [0, 1] and maps NaN to 0', () => {
		expect([clamp01(-1), clamp01(0.4), clamp01(9), clamp01(NaN)]).toEqual([0, 0.4, 1, 0]);
	});
});

describe('bisectTime', () => {
	const times = [10, 20, 30, 40];
	it('finds exact and nearest entries', () => {
		expect(bisectTime(times, 30)).toBe(2);
		expect(bisectTime(times, 26)).toBe(2);
		expect(bisectTime(times, 24)).toBe(1);
	});
	it('breaks ties towards the earlier entry and clamps at the ends', () => {
		expect(bisectTime(times, 25)).toBe(1);
		expect(bisectTime(times, -100)).toBe(0);
		expect(bisectTime(times, 1e9)).toBe(3);
	});
	it('returns -1 for no data', () => {
		expect(bisectTime([], 5)).toBe(-1);
	});
});

describe('columnDecimate', () => {
	const make = (n: number) => {
		const times = Float64Array.from({ length: n }, (_, i) => 1_600_000_000 + i * 60);
		const values = Array.from({ length: n }, (_, i) => Math.sin(i / 50));
		return { times, values };
	};

	it('keeps everything when there is room', () => {
		const { times, values } = make(100);
		expect(columnDecimate(times, values, 100)).toHaveLength(100);
	});

	it('bounds the output and keeps an injected spike and trough', () => {
		const { times, values } = make(100_000);
		values[61_234] = 50;
		values[12_345] = -50;
		const kept = columnDecimate(times, values, 400);
		expect(kept.length).toBeLessThanOrEqual(400 * 4);
		expect(kept).toContain(61_234);
		expect(kept).toContain(12_345);
		expect(kept).toContain(0);
		expect(kept).toContain(99_999);
		expect(kept.every((v, i) => i === 0 || v > kept[i - 1])).toBe(true);
	});

	it('keeps a single marker per gap so the line can still break', () => {
		const { times, values } = make(5_000);
		const holed: (number | null)[] = [...values];
		for (let i = 2_000; i < 2_600; i++) holed[i] = null;
		const kept = columnDecimate(times, holed, 200);
		const gaps = kept.filter((i) => holed[i] === null);
		expect(gaps).toHaveLength(1);
		expect(kept.length).toBeLessThan(200 * 4 + 2);
	});

	it('buckets by time, so uneven spacing does not distort columns', () => {
		const times = Float64Array.from({ length: 2_000 }, (_, i) =>
			i < 1_000 ? i : 1_000 + (i - 1_000) * 100
		);
		const values = Array.from({ length: 2_000 }, (_, i) => i % 7);
		const kept = columnDecimate(times, values, 100);
		expect(kept.length).toBeLessThanOrEqual(100 * 4);
		expect(kept).toContain(0);
		expect(kept).toContain(1_999);
	});
});

describe('path builders', () => {
	const x = (i: number) => i * 10;
	const y = (v: number) => 100 - v;
	const all = (n: number) => Array.from({ length: n }, (_, i) => i);

	it('draws a continuous line', () => {
		expect(linePath(all(3), [1, 2, 3], x, y)).toBe('M0 99L10 98L20 97');
	});
	it('starts a new subpath after null and NaN without emitting NaN', () => {
		const d = linePath(all(6), [1, null, 3, 4, NaN, 6], x, y);
		expect(d).not.toContain('NaN');
		expect(d.match(/M/g)).toHaveLength(3);
	});
	it('turns an isolated point into a zero-length dot', () => {
		expect(linePath(all(3), [null, 5, null], x, y)).toBe('M10 95h0');
	});
	it('splits segments on gaps', () => {
		expect(segments(all(5), [1, 2, null, 4, 5])).toEqual([
			[0, 1],
			[3, 4]
		]);
	});
	it('closes every area run to the baseline', () => {
		const d = areaPath(all(5), [1, 2, null, 4, 5], x, y, 100);
		expect(d).toBe('M0 100L0 99L10 98L10 100ZM30 100L30 96L40 95L40 100Z');
	});
	it('skips single-point area runs', () => {
		expect(areaPath(all(3), [null, 5, null], x, y, 100)).toBe('');
	});
});

describe('timeTicks', () => {
	it('aligns daily ticks to UTC midnights', () => {
		const ticks = timeTicks(utc('2024-05-01T05:00:00Z'), utc('2024-05-08T05:00:00Z'), 8);
		expect(ticks[0]).toBe(utc('2024-05-02T00:00:00Z'));
		expect(ticks.every((t) => t % DAY === 0)).toBe(true);
		expect(ticks.length).toBeGreaterThanOrEqual(4);
		expect(ticks.length).toBeLessThanOrEqual(8);
	});
	it('uses sub-day steps for short spans and flags the time of day', () => {
		const t0 = utc('2024-05-01T00:10:00Z');
		const t1 = utc('2024-05-01T23:50:00Z');
		expect(showsTimeOfDay(t0, t1)).toBe(true);
		const ticks = timeTicks(t0, t1, 6);
		expect(ticks.length).toBeGreaterThan(2);
		expect(ticks.length).toBeLessThanOrEqual(6);
		expect(ticks[1] - ticks[0]).toBeGreaterThanOrEqual(3600);
	});
	it('never goes below a day once the span reaches three days', () => {
		const t0 = utc('2024-05-01T00:00:00Z');
		const t1 = t0 + 3 * DAY;
		expect(showsTimeOfDay(t0, t1)).toBe(false);
		const ticks = timeTicks(t0, t1, 30);
		expect(ticks[1] - ticks[0]).toBeGreaterThanOrEqual(DAY);
	});
	it('lands weekly ticks on Mondays', () => {
		const ticks = timeTicks(utc('2024-01-01T00:00:00Z'), utc('2024-03-20T00:00:00Z'), 12);
		const days = new Set(ticks.map((t) => new Date(t * 1000).getUTCDay()));
		expect([...days]).toEqual([1]);
	});
	it('uses month starts across a year', () => {
		const ticks = timeTicks(utc('2023-01-15T00:00:00Z'), utc('2024-01-15T00:00:00Z'), 7);
		expect(ticks.length).toBeGreaterThan(2);
		expect(ticks.every((t) => new Date(t * 1000).getUTCDate() === 1)).toBe(true);
	});
	it('uses January 1st for multi-year spans', () => {
		const ticks = timeTicks(utc('2015-06-01T00:00:00Z'), utc('2024-06-01T00:00:00Z'), 8);
		expect(
			ticks.every((t) => t === utc(`${new Date(t * 1000).getUTCFullYear()}-01-01T00:00:00Z`))
		).toBe(true);
		expect(ticks.length).toBeLessThanOrEqual(8);
	});
	it('handles degenerate input', () => {
		expect(timeTicks(5, 5, 6)).toEqual([5]);
		expect(timeTicks(NaN, 5, 6)).toEqual([]);
	});
});

describe('label layout', () => {
	it('keeps nudged labels at least `gap` apart, in input order', () => {
		const out = nudgeApart([50, 52, 10, 51], 14, 0, 200);
		const sorted = [...out].sort((a, b) => a - b);
		for (let i = 1; i < sorted.length; i++)
			expect(sorted[i] - sorted[i - 1]).toBeGreaterThanOrEqual(14 - 1e-9);
		expect(out[2]).toBeLessThan(out[0]);
	});
	it('pushes labels back inside the bounds', () => {
		const out = nudgeApart([195, 198, 199], 14, 0, 200);
		expect(Math.max(...out)).toBeLessThanOrEqual(200);
		expect(Math.min(...out)).toBeGreaterThanOrEqual(200 - 2 * 14 - 1e-9);
	});
	it('stacks overlapping captions into rows', () => {
		const rows = assignRows([
			{ start: 0, end: 50 },
			{ start: 40, end: 90 },
			{ start: 100, end: 140 }
		]);
		expect(rows).toEqual([0, 1, 0]);
	});
});

describe('stepIndex', () => {
	it('moves along x with the arrow keys and clamps', () => {
		expect(stepIndex('ArrowRight', 3, 10, { axis: 'x' })).toBe(4);
		expect(stepIndex('ArrowLeft', 0, 10, { axis: 'x' })).toBe(0);
		expect(stepIndex('ArrowRight', 9, 10, { axis: 'x' })).toBe(9);
	});
	it('starts from the matching end when nothing is selected', () => {
		expect(stepIndex('ArrowRight', null, 10, { axis: 'x' })).toBe(0);
		expect(stepIndex('ArrowLeft', null, 10, { axis: 'x' })).toBe(9);
	});
	it('supports Home, End and paging', () => {
		expect(stepIndex('Home', 5, 10, { axis: 'x' })).toBe(0);
		expect(stepIndex('End', 5, 10, { axis: 'x' })).toBe(9);
		expect(stepIndex('PageDown', 0, 100, { axis: 'x' })).toBe(10);
		expect(stepIndex('PageUp', 50, 100, { axis: 'x' })).toBe(40);
		expect(stepIndex('PageUp', 50, 100, { axis: 'y' })).toBe(60);
	});
	it('treats ArrowUp as a higher index on the y axis', () => {
		expect(stepIndex('ArrowUp', 2, 10, { axis: 'y' })).toBe(3);
		expect(stepIndex('ArrowDown', 2, 10, { axis: 'y' })).toBe(1);
		expect(stepIndex('ArrowLeft', 2, 10, { axis: 'y' })).toBeNull();
	});
	it('ignores other keys and empty charts', () => {
		expect(stepIndex('a', 1, 10, { axis: 'x' })).toBeNull();
		expect(stepIndex('ArrowRight', null, 0, { axis: 'x' })).toBeNull();
	});
});

describe('binIndex', () => {
	const edges = [0, 10, 20, 30];
	it('finds the containing bin and treats an edge as the start of the next bin', () => {
		expect(binIndex(edges, 5)).toBe(0);
		expect(binIndex(edges, 10)).toBe(1);
		expect(binIndex(edges, 29.9)).toBe(2);
	});
	it('clamps outside the range and handles degenerate edges', () => {
		expect(binIndex(edges, -5)).toBe(0);
		expect(binIndex(edges, 99)).toBe(2);
		expect(binIndex([1], 1)).toBe(-1);
	});
});

describe('formatNumber', () => {
	it('formats with separators and an em dash for missing values', () => {
		expect(formatNumber(1234567.891)).toBe('1,234,570');
		expect(formatNumber(0.5)).toBe('0.5');
		expect(formatNumber(null)).toBe('\u2014');
	});
});

describe('heatmap colour ramps', () => {
	it('build colours from tokens only', () => {
		for (const t of [0, 0.2, 0.5, 0.8, 1]) {
			for (const c of [sequentialColor(t), divergingColor(t)]) {
				expect(c).toMatch(/^color-mix\(in oklab, var\(--[\w-]+\) [\d.]+%, var\(--[\w-]+\)\)$/);
				expect(c).not.toContain('#');
			}
		}
	});
	const mix = (top: string, pct: number, base: string) =>
		`color-mix(in oklab, var(--${top}) ${pct}%, var(--${base}))`;
	it('runs surface-2 to violet to magenta to orange', () => {
		expect(sequentialColor(0)).toBe(mix('gradient-violet', 0, 'surface-2'));
		expect(sequentialColor(1 / 6)).toBe(mix('gradient-violet', 50, 'surface-2'));
		expect(sequentialColor(1 / 3)).toBe(mix('gradient-magenta', 0, 'gradient-violet'));
		expect(sequentialColor(0.5)).toBe(mix('gradient-magenta', 50, 'gradient-violet'));
		expect(sequentialColor(5 / 6)).toBe(mix('gradient-orange', 50, 'gradient-magenta'));
		expect(sequentialColor(1)).toBe(mix('gradient-orange', 100, 'gradient-magenta'));
	});
	it('has coral, a neutral midpoint and success on the diverging ramp', () => {
		expect(divergingColor(0)).toBe(mix('surface-2', 0, 'gradient-coral'));
		expect(divergingColor(0.25)).toBe(mix('surface-2', 50, 'gradient-coral'));
		expect(divergingColor(0.5)).toBe(mix('semantic-success', 0, 'surface-2'));
		expect(divergingColor(0.75)).toBe(mix('semantic-success', 50, 'surface-2'));
		expect(divergingColor(1)).toBe(mix('semantic-success', 100, 'surface-2'));
	});
	it('clamps out-of-range input', () => {
		expect(sequentialColor(-5)).toBe(sequentialColor(0));
		expect(sequentialColor(7)).toBe(sequentialColor(1));
	});
	it('gets lighter along the sequential ramp', () => {
		let previous = -1;
		for (let i = 0; i <= 100; i++) {
			const y = heatLuminance(i / 100, 'sequential');
			expect(y).toBeGreaterThanOrEqual(previous - 1e-9);
			previous = y;
		}
	});
	const THEMES = ['dark', 'light'] as const;
	it.each(THEMES)('keeps text at 4.5:1 or better on every cell of both scales (%s)', (theme) => {
		for (const scale of ['sequential', 'diverging'] as const) {
			for (let i = 0; i <= 1000; i++) {
				const t = i / 1000;
				const ink = contrastInk(t, scale, theme);
				const key = ink === 'var(--ink)' ? 'ink' : 'on-primary';
				expect(heatContrast(t, scale, key, theme), `${theme} ${scale} ${t}`).toBeGreaterThanOrEqual(
					4.5
				);
			}
		}
	});
	it('picks white on dark cells and black on light ones (dark theme)', () => {
		expect(contrastInk(0, 'sequential')).toBe('var(--ink)');
		expect(contrastInk(1, 'sequential')).toBe('var(--on-primary)');
		expect(contrastInk(0.5, 'diverging')).toBe('var(--ink)');
		expect(contrastInk(0, 'sequential', 'dark')).toBe('var(--ink)');
	});
	it('picks near-black ink on the pale light-theme start of a ramp and white on saturated stops', () => {
		// Light: --ink is near-black and --on-primary is white, the reverse of dark.
		expect(contrastInk(0, 'sequential', 'light')).toBe('var(--ink)');
		expect(contrastInk(0.5, 'diverging', 'light')).toBe('var(--ink)');
		expect(contrastInk(1 / 3, 'sequential', 'light')).toBe('var(--on-primary)');
		expect(contrastInk(0, 'diverging', 'light')).not.toBe(contrastInk(0, 'diverging', 'dark'));
	});
	it('computes the same cell differently per theme (the ramp starts at surface-2)', () => {
		expect(heatLuminance(0, 'sequential', 'light')).toBeGreaterThan(
			heatLuminance(0, 'sequential', 'dark')
		);
		expect(heatLuminance(1, 'sequential', 'light')).toBeCloseTo(
			heatLuminance(1, 'sequential', 'dark'),
			6
		);
	});
	it.each(THEMES)('mirrors the layout.css tokens (%s)', (theme) => {
		const css = readFileSync(
			fileURLToPath(new URL('../../routes/layout.css', import.meta.url)),
			'utf8'
		);
		const block =
			theme === 'dark'
				? /:root\s*\{([\s\S]*?)\n\}/.exec(css)![1]
				: /:root\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/.exec(css)![1];
		for (const [token, rgb] of Object.entries(TOKEN_RGB[theme])) {
			// Tokens the light block does not override are inherited from :root.
			const source = new RegExp(`${token}:`).test(block)
				? block
				: /:root\s*\{([\s\S]*?)\n\}/.exec(css)![1];
			const hex = new RegExp(`${token}:\\s*#([0-9a-fA-F]{6});`).exec(source)?.[1];
			expect(hex, `${theme} ${token}`).toBeDefined();
			const parsed = [0, 2, 4].map((i) => parseInt(hex!.slice(i, i + 2), 16));
			expect(parsed, `${theme} ${token}`).toEqual([...rgb]);
		}
	});
});

describe('normalize', () => {
	it('scales sequential values linearly and clamps', () => {
		expect(normalize(5, [0, 10], 'sequential')).toBe(0.5);
		expect(normalize(-3, [0, 10], 'sequential')).toBe(0);
		expect(normalize(99, [0, 10], 'sequential')).toBe(1);
		expect(normalize(4, [4, 4], 'sequential')).toBe(0.5);
	});
	it('keeps zero at the midpoint for diverging scales, even with an asymmetric domain', () => {
		expect(normalize(0, [-1, 1], 'diverging')).toBe(0.5);
		expect(normalize(-1, [-1, 1], 'diverging')).toBe(0);
		expect(normalize(1, [-1, 1], 'diverging')).toBe(1);
		expect(normalize(0, [-2, 8], 'diverging')).toBe(0.5);
		expect(normalize(-2, [-2, 8], 'diverging')).toBe(0);
		expect(normalize(4, [-2, 8], 'diverging')).toBe(0.75);
		expect(normalize(5, [0, 0], 'diverging')).toBe(0.5);
	});
});
