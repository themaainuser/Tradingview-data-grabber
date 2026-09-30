import { describe, expect, it } from 'vitest';
import { userEvent } from 'vitest/browser';
import AreaChart from './AreaChart.svelte';
import type { AreaSeries } from './types';
import { mountChart, paintOf, pathPoints, pointer, tooltipEl, tooltipText } from './test-utils';

const DAY = 86_400;
const T0 = Date.UTC(2024, 4, 1) / 1000;
const days = (n: number) => Array.from({ length: n }, (_, i) => T0 + i * DAY);

const price: AreaSeries = {
	key: 'price',
	label: 'Price',
	color: 'var(--ink)',
	values: [10, 20, 15, 30, 25]
};
const svg = () => document.querySelector('svg')!;
const linePaths = () => [...document.querySelectorAll<SVGPathElement>('path[data-kind="line"]')];
const group = () => document.querySelector<HTMLElement>('[role="group"]')!;
const live = () => document.querySelector('[aria-live="polite"]')!;

/** Client x of the plot's fraction `f` (0..1), read from the rendered geometry. */
function plotX(f: number) {
	const box = svg().getBoundingClientRect();
	const transform = svg().querySelector('g')!.getAttribute('transform')!;
	const left = Number(/translate\(([\d.]+)/.exec(transform)![1]);
	const grid = svg().querySelector('line.stroke-hairline')!;
	return box.left + left + Number(grid.getAttribute('x2')) * f;
}
const hover = (f: number) =>
	pointer('pointermove', group(), plotX(f), svg().getBoundingClientRect().top + 60);

describe('AreaChart', () => {
	it('renders at the measured width and the requested height, one line per series', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [price, { ...price, key: 'b', label: 'B', values: [1, 2, 3, 4, 5] }],
				height: 240,
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('600');
		expect(svg().getAttribute('height')).toBe('240');
		expect(linePaths()).toHaveLength(2);
		expect(document.querySelectorAll('path[data-kind="area"]')).toHaveLength(0);
	});

	it('follows its container when the width changes', async () => {
		const { resize } = mountChart(
			AreaChart,
			{ time: days(5), series: [price], label: 'Test chart' },
			600
		);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('600');
		const before = linePaths()[0].getAttribute('d');
		resize(320);
		await expect.poll(() => svg().getAttribute('width')).toBe('320');
		expect(linePaths()[0].getAttribute('d')).not.toBe(before);
	});

	it('draws area series with a gradient fill and a baseline reference line', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [{ ...price, kind: 'area', values: [-5, 10, 20, 5, -10] }],
				baseline: 0,
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => document.querySelectorAll('path[data-kind="area"]').length).toBe(1);
		const fill = document.querySelector<SVGPathElement>('path[data-kind="area"]')!;
		expect(fill.style.fill).toMatch(/^url\(/);
		expect(document.querySelector('linearGradient')).not.toBeNull();
		expect(svg().querySelector('line[stroke-dasharray="3 3"]')).not.toBeNull();
	});

	it('breaks the line at null values without emitting NaN', async () => {
		mountChart(
			AreaChart,
			{
				time: days(7),
				series: [{ ...price, values: [1, 2, null, 4, NaN, 6, 7] }],
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => linePaths().length).toBe(1);
		const d = linePaths()[0].getAttribute('d')!;
		expect(d).not.toContain('NaN');
		expect(d.match(/M/g)).toHaveLength(3);
	});

	it('decimates dense series per pixel column but keeps a spike', async () => {
		const n = 20_000;
		const values = Array.from({ length: n }, (_, i) => 50 + 10 * Math.sin(i / 40));
		values[13_337] = 100;
		mountChart(
			AreaChart,
			{
				time: Array.from({ length: n }, (_, i) => T0 + i * 60),
				series: [{ ...price, values }],
				leftDomain: [0, 100],
				label: 'Test chart'
			},
			500
		);
		await expect.poll(() => linePaths().length).toBe(1);
		const points = pathPoints(linePaths()[0].getAttribute('d'));
		expect(points.length).toBeGreaterThan(100);
		expect(points.length).toBeLessThan(4 * 500);
		// y = 0 is the plot top, where only the spike (value 100) can be.
		expect(Math.min(...points.map((p) => p.y))).toBe(0);
	});

	it('only paints with design tokens', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [
					{ ...price, kind: 'area', color: 'var(--gradient-violet)' },
					{
						...price,
						key: 'b',
						label: 'B',
						axis: 'right',
						color: 'var(--gradient-orange)',
						dashed: true
					}
				],
				bands: [{ from: 10, to: 20, color: 'var(--semantic-success)', label: 'Zone' }],
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => linePaths().length).toBe(2);
		const painted = [...svg().querySelectorAll('*')].flatMap(paintOf);
		expect(painted.length).toBeGreaterThan(5);
		for (const value of painted) expect(value.replace(/url\([^)]*\)/g, '')).not.toMatch(/#|rgb\(/);
		expect(linePaths()[0].style.stroke).toBe('var(--gradient-violet)');
	});

	it('draws bands behind the series with their label', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [price],
				bands: [{ from: 12, to: 22, color: 'var(--gradient-coral)', label: 'Fear zone' }],
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => document.querySelectorAll('rect[data-band]').length).toBe(1);
		const band = document.querySelector('rect[data-band]')!;
		expect(band.getAttribute('fill-opacity')).toBe('0.14');
		expect(
			band.compareDocumentPosition(linePaths()[0]) & Node.DOCUMENT_POSITION_FOLLOWING
		).toBeTruthy();
		expect(svg().textContent).toContain('Fear zone');
	});

	it('puts right-axis series on their own scale and format', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [
					price,
					{
						...price,
						key: 'vol',
						label: 'Volume',
						axis: 'right',
						values: [100, 200, 150, 300, 250]
					}
				],
				rightFormat: (v: number) => `${v} shares`,
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => linePaths().length).toBe(2);
		const right = [...svg().querySelectorAll('text')].filter((t) =>
			t.textContent?.endsWith(' shares')
		);
		expect(right.length).toBeGreaterThan(1);
		hover(0.5);
		await expect.poll(tooltipText).toContain('150 shares');
	});

	it('shows a tooltip with the time and each value on pointer move', async () => {
		mountChart(
			AreaChart,
			{
				time: days(5),
				series: [
					price,
					{
						...price,
						key: 'b',
						label: 'Other',
						color: 'var(--gradient-magenta)',
						values: [1, 2, null, 4, 5]
					}
				],
				leftFormat: (v: number) => `$${v}`,
				label: 'Test chart'
			},
			600
		);
		await expect.poll(() => linePaths().length).toBe(2);
		expect(tooltipEl()).toBeNull();
		hover(0.5);
		await expect.poll(tooltipText).toContain('2024-05-03');
		expect(tooltipText()).toContain('Price');
		expect(tooltipText()).toContain('$15');
		expect(tooltipText()).toContain('Other');
		expect(tooltipText()).toContain('\u2014');
		expect(svg().querySelector('[data-cursor]')).not.toBeNull();
		group().dispatchEvent(new PointerEvent('pointerleave'));
		await expect.poll(tooltipEl).toBeNull();
	});

	it('labels the time axis with the time of day for short spans', async () => {
		mountChart(
			AreaChart,
			{
				time: Array.from({ length: 24 }, (_, i) => T0 + i * 3600),
				series: [{ ...price, values: Array.from({ length: 24 }, (_, i) => i) }],
				label: 'Test chart'
			},
			700
		);
		await expect.poll(() => linePaths().length).toBe(1);
		const labels = [...svg().querySelectorAll('text')].map((t) => t.textContent ?? '');
		expect(labels.some((t) => /^\d{4}-\d\d-\d\d \d\d:\d\d$/.test(t))).toBe(true);
		hover(0.5);
		await expect.poll(tooltipText).toContain('UTC');
	});

	it('labels the time axis with dates only for long spans', async () => {
		mountChart(
			AreaChart,
			{
				time: days(40),
				series: [{ ...price, values: days(40).map((_, i) => i) }],
				label: 'Test chart'
			},
			700
		);
		await expect.poll(() => linePaths().length).toBe(1);
		const labels = [...svg().querySelectorAll('text')].map((t) => t.textContent ?? '');
		expect(labels.some((t) => /^\d{4}-\d\d-\d\d$/.test(t))).toBe(true);
		expect(labels.some((t) => /\d\d:\d\d/.test(t))).toBe(false);
	});

	it('is keyboard operable and announces values', async () => {
		mountChart(AreaChart, { time: days(5), series: [price], label: 'Test chart' }, 600);
		await expect.poll(() => linePaths().length).toBe(1);
		expect(group().getAttribute('tabindex')).toBe('0');
		expect(group().getAttribute('aria-label')).toBe('Test chart');

		group().focus();
		expect(document.activeElement).toBe(group());
		await expect.poll(tooltipText).toContain('2024-05-05');
		expect(tooltipText()).toContain('25');

		await userEvent.keyboard('{ArrowLeft}');
		await expect.poll(tooltipText).toContain('2024-05-04');
		expect(tooltipText()).toContain('30');
		expect(live().textContent).toContain('2024-05-04');
		expect(live().textContent).toContain('Price 30');

		await userEvent.keyboard('{Home}');
		await expect.poll(tooltipText).toContain('2024-05-01');
		await userEvent.keyboard('{End}');
		await expect.poll(tooltipText).toContain('2024-05-05');
		await userEvent.keyboard('{Escape}');
		await expect.poll(tooltipEl).toBeNull();
	});

	it('keeps the global focus ring and the readout after a touch ends', async () => {
		mountChart(AreaChart, { time: days(5), series: [price], label: 'Test chart' }, 600);
		await expect.poll(() => linePaths().length).toBe(1);
		group().focus();
		expect(getComputedStyle(group()).boxShadow).not.toBe('none');
		expect(getComputedStyle(group()).boxShadow).toContain('rgb(0, 153, 255)');
		hover(0.5);
		await expect.poll(tooltipText).toContain('2024-05-03');
		group().dispatchEvent(new PointerEvent('pointerleave', { pointerType: 'touch' }));
		await new Promise((r) => setTimeout(r, 50));
		expect(tooltipEl()).not.toBeNull();
		group().blur();
		await expect.poll(tooltipEl).toBeNull();
	});

	it('exposes a screen-reader summary of the data', async () => {
		mountChart(AreaChart, { time: days(5), series: [price], label: 'Test chart' }, 600);
		await expect.poll(() => linePaths().length).toBe(1);
		const summary = document.querySelector('p.sr-only')!;
		expect(summary.textContent).toContain('Test chart');
		expect(summary.textContent).toContain('5 points');
		expect(summary.textContent).toContain('latest 25');
		expect(summary.textContent).toContain('low 10');
		expect(summary.textContent).toContain('high 30');
		expect(live().getAttribute('aria-atomic')).toBe('true');
	});

	it('renders without data', async () => {
		mountChart(AreaChart, { time: [], series: [{ ...price, values: [] }], label: 'Empty' }, 400);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('400');
		expect(linePaths()).toHaveLength(0);
		expect(document.querySelector('p.sr-only')!.textContent).toContain('no data');
	});
});
