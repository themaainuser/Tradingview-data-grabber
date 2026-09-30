import { afterEach, describe, expect, it } from 'vitest';
import { userEvent } from 'vitest/browser';
import {
	contrastInk,
	divergingColor,
	heatLinearRgb,
	normalize,
	sequentialColor
} from '$lib/charts/chart-math';
import Heatmap from './Heatmap.svelte';
import { mountChart, paintOf, pointer, tooltipEl, tooltipText } from './test-utils';

const rows = ['AAA', 'BBB', 'CCC'];
const cols = ['x1', 'x2', 'x3', 'x4'];
const values = [
	[0, 0.25, 0.5, 1],
	[0.1, null, 0.6, 0.9],
	[0.2, 0.3, 0.4, 0.8]
];
const cellsEl = () => [...document.querySelectorAll<HTMLElement>('[role="gridcell"]')];
const cell = (r: number, c: number) =>
	document.querySelector<HTMLElement>(`[data-r="${r}"][data-c="${c}"]`)!;
const printed = () => cellsEl().filter((c) => c.textContent?.trim()).length;
const base = { rows, cols, values, label: 'Test heatmap' };

afterEach(() => document.documentElement.removeAttribute('data-theme'));

describe('Heatmap', () => {
	it('renders one gridcell per row and column, with headers', async () => {
		mountChart(Heatmap, base, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		const grid = document.querySelector('[role="grid"]')!;
		expect(grid.getAttribute('aria-label')).toBe('Test heatmap');
		expect(grid.getAttribute('aria-rowcount')).toBe('4');
		expect(grid.getAttribute('aria-colcount')).toBe('5');
		expect(
			[...document.querySelectorAll('[role="rowheader"]')].map((e) => e.textContent?.trim())
		).toEqual(rows);
		expect(document.querySelectorAll('[role="columnheader"]')).toHaveLength(5);
		expect(cell(1, 2).getAttribute('aria-label')).toBe('BBB, x3: 0.6');
	});

	it('sizes cells from the container width and cellHeight', async () => {
		const { resize } = mountChart(Heatmap, { ...base, cellHeight: 30 }, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		const wide = cell(0, 0).getBoundingClientRect();
		expect(wide.height).toBe(30);
		resize(300);
		await expect.poll(() => cell(0, 0).getBoundingClientRect().width).toBeLessThan(wide.width);
	});

	it('keeps cells square when asked, capped at 64px', async () => {
		mountChart(Heatmap, { ...base, square: true }, 900);
		await expect.poll(() => cellsEl().length).toBe(12);
		const box = cell(0, 0).getBoundingClientRect();
		expect(box.width).toBe(64);
		expect(box.height).toBe(64);
	});

	it('paints cells with token-based colour mixes only, and leaves null cells empty', async () => {
		mountChart(Heatmap, base, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		const painted = [...document.querySelectorAll('[role="grid"] *')].flatMap(paintOf);
		expect(painted.length).toBeGreaterThan(10);
		for (const value of painted) expect(value).not.toMatch(/#|rgb\(/);
		expect(cell(0, 3).getAttribute('style')).toContain('color-mix(in oklab');
		expect(cell(0, 3).getAttribute('style')).toContain('var(--gradient-orange) 100%');
		const empty = cell(1, 1);
		expect(empty.style.background).toBe('');
		expect(empty.getAttribute('aria-label')).toBe('BBB, x2: no data');
		expect(empty.querySelector('span')).not.toBeNull();
	});

	it('keeps zero at the neutral midpoint on a diverging scale', async () => {
		mountChart(
			Heatmap,
			{
				rows: ['r'],
				cols: ['neg', 'zero', 'pos'],
				values: [[-0.8, 0, 0.8]],
				scale: 'diverging',
				label: 'Diverging'
			},
			600
		);
		await expect.poll(() => cellsEl().length).toBe(3);
		const bg = (c: number) => cell(0, c).getAttribute('style')!;
		expect(bg(0)).toContain('var(--surface-2) 0%, var(--gradient-coral)');
		expect(bg(1)).toContain('var(--semantic-success) 0%, var(--surface-2)');
		expect(bg(2)).toContain('var(--semantic-success) 100%');
	});

	it('prints values only while cells are big enough for them', async () => {
		const { resize } = mountChart(
			Heatmap,
			{ ...base, showValues: true, format: (v: number) => v.toFixed(2) },
			600
		);
		await expect.poll(printed).toBe(11);
		expect(cell(0, 3).textContent).toContain('1.00');
		resize(120);
		await expect.poll(printed).toBe(0);
		resize(600);
		await expect.poll(printed).toBe(11);
	});

	it('does not print values unless asked', async () => {
		mountChart(Heatmap, base, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		expect(printed()).toBe(0);
	});

	it('picks white text on dark cells and black on light ones', async () => {
		mountChart(Heatmap, { ...base, showValues: true }, 600);
		await expect.poll(printed).toBe(11);
		expect(cell(0, 0).querySelector('span')!.getAttribute('style')).toContain('var(--ink)');
		expect(cell(0, 3).querySelector('span')!.getAttribute('style')).toContain('var(--on-primary)');
	});

	it.each(['dark', 'light'] as const)('picks cell text for the %s theme', async (theme) => {
		document.documentElement.setAttribute('data-theme', theme);
		mountChart(Heatmap, { ...base, showValues: true }, 600);
		await expect.poll(printed).toBe(11);
		// Domain is the data extent, [0, 1], so a cell's value is its position on the ramp.
		for (const [r, c, v] of [
			[0, 0, 0],
			[0, 1, 0.25],
			[0, 2, 0.5],
			[0, 3, 1]
		] as const) {
			const t = normalize(v, [0, 1], 'sequential');
			expect(cell(r, c).querySelector('span')!.getAttribute('style'), `${theme} ${v}`).toContain(
				contrastInk(t, 'sequential', theme)
			);
		}
	});

	it('repaints the cell text when the theme flips after mount', async () => {
		// One row; the domain is [0, 1], so 1/3 is the pure violet stop of the ramp.
		mountChart(
			Heatmap,
			{
				rows: ['r'],
				cols: ['a', 'b', 'c'],
				values: [[1 / 3, 0, 1]],
				label: 'Flip',
				showValues: true
			},
			600
		);
		await expect.poll(printed).toBe(3);
		const ink = () => cell(0, 0).querySelector('span')!.getAttribute('style');
		const dark = contrastInk(1 / 3, 'sequential', 'dark');
		const light = contrastInk(1 / 3, 'sequential', 'light');
		// The cell is chosen so the two themes disagree; otherwise this test would prove nothing.
		expect(dark).not.toBe(light);
		expect(ink()).toContain(dark);
		document.documentElement.setAttribute('data-theme', 'light');
		await expect.poll(ink).toContain(light);
		document.documentElement.setAttribute('data-theme', 'dark');
		await expect.poll(ink).toContain(dark);
	});

	it('has a roving tabindex and moves focus with the arrow keys', async () => {
		mountChart(Heatmap, base, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		expect(cellsEl().filter((c) => c.getAttribute('tabindex') === '0')).toHaveLength(1);
		expect(cell(0, 0).getAttribute('tabindex')).toBe('0');

		cell(0, 0).focus();
		await expect.poll(tooltipText).toContain('AAA \u00d7 x1');
		await userEvent.keyboard('{ArrowRight}');
		expect(document.activeElement).toBe(cell(0, 1));
		await expect.poll(tooltipText).toContain('AAA \u00d7 x2');
		expect(tooltipText()).toContain('0.25');
		expect(cell(0, 1).getAttribute('tabindex')).toBe('0');
		expect(cell(0, 0).getAttribute('tabindex')).toBe('-1');

		await userEvent.keyboard('{ArrowDown}');
		expect(document.activeElement).toBe(cell(1, 1));
		await expect.poll(tooltipText).toContain('\u2014');
		await userEvent.keyboard('{End}');
		expect(document.activeElement).toBe(cell(1, 3));
		await userEvent.keyboard('{Home}');
		expect(document.activeElement).toBe(cell(1, 0));
		await userEvent.keyboard('{Control>}{End}{/Control}');
		expect(document.activeElement).toBe(cell(2, 3));
		await userEvent.keyboard('{ArrowRight}{ArrowDown}');
		expect(document.activeElement).toBe(cell(2, 3));
	});

	it('shows row, column and value in a tooltip on hover', async () => {
		mountChart(Heatmap, { ...base, format: (v: number) => `${Math.round(v * 100)}%` }, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		expect(tooltipEl()).toBeNull();
		pointer('pointerover', cell(2, 2), 0, 0);
		await expect.poll(tooltipText).toContain('CCC \u00d7 x3');
		expect(tooltipText()).toContain('40%');
		expect(cell(2, 2).dataset.active).toBe('true');
		document.querySelector('[role="grid"]')!.dispatchEvent(new PointerEvent('pointerleave'));
		await expect.poll(tooltipEl).toBeNull();
	});

	it('draws a gradient legend under the grid only when requested', async () => {
		const { host } = mountChart(Heatmap, { ...base, legend: { low: 'Weak', high: 'Strong' } }, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		expect(host.textContent).toContain('Weak');
		expect(host.textContent).toContain('Strong');
		expect(host.querySelector('.h-2')!.getAttribute('style')).toContain('linear-gradient');
	});

	it('thins column labels but keeps every header readable', async () => {
		const many = Array.from({ length: 30 }, (_, i) => `2024-${String(i + 1).padStart(2, '0')}`);
		mountChart(
			Heatmap,
			{ rows: ['r'], cols: many, values: [many.map((_, i) => i)], label: 'Wide' },
			500
		);
		await expect.poll(() => cellsEl().length).toBe(30);
		const headers = [...document.querySelectorAll('[role="columnheader"] span:not(.sr-only)')];
		expect(headers.length).toBeGreaterThan(1);
		expect(headers.length).toBeLessThan(15);
		expect(document.querySelectorAll('[role="columnheader"]')).toHaveLength(31);
		const every5 = mountChart(
			Heatmap,
			{
				rows: ['r'],
				cols: many,
				values: [many.map((_, i) => i)],
				colLabelEvery: 5,
				label: 'Wide 2'
			},
			500
		);
		await expect
			.poll(() => every5.host.querySelectorAll('[role="columnheader"] span:not(.sr-only)').length)
			.toBe(6);
	});

	it('exposes a screen-reader summary', async () => {
		mountChart(Heatmap, base, 600);
		await expect.poll(() => cellsEl().length).toBe(12);
		const summary = document.querySelector('p.sr-only')!.textContent!;
		expect(summary).toContain('Test heatmap');
		expect(summary).toContain('3 rows by 4 columns');
		expect(summary).toContain('from 0 to 1');
	});

	it('renders without rows or columns', async () => {
		const { host } = mountChart(Heatmap, { rows: [], cols: [], values: [], label: 'Empty' }, 300);
		await expect.poll(() => host.querySelector('p.sr-only')?.textContent).toContain('no data');
		expect(cellsEl()).toHaveLength(0);
	});
});

describe('heatmap colour maths', () => {
	// The JS luminance behind the text-contrast choice must match what the browser paints.
	const srgb = (linear: number) =>
		255 * (linear <= 0.0031308 ? linear * 12.92 : 1.055 * linear ** (1 / 2.4) - 0.055);

	function painted(css: string): number[] {
		const probe = document.createElement('div');
		probe.style.background = css;
		document.body.append(probe);
		const computed = getComputedStyle(probe).backgroundColor;
		probe.remove();
		const ctx = document.createElement('canvas').getContext('2d', { willReadFrequently: true })!;
		ctx.fillStyle = computed;
		ctx.fillRect(0, 0, 1, 1);
		return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
	}

	it.each([
		['sequential', sequentialColor, [0, 0.1, 0.25, 0.4, 0.6, 0.8, 1]],
		['diverging', divergingColor, [0, 0.2, 0.45, 0.5, 0.7, 1]]
	] as const)('matches the browser for the %s ramp', (scale, color, steps) => {
		for (const t of steps) {
			const expected = heatLinearRgb(t, scale).map(srgb);
			const actual = painted(color(t));
			actual.forEach((channel, i) =>
				expect(Math.abs(channel - expected[i]), `${scale} ${t}`).toBeLessThanOrEqual(3)
			);
		}
	});
});
