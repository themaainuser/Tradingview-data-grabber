import { describe, expect, it } from 'vitest';
import { userEvent } from 'vitest/browser';
import BarChart from './BarChart.svelte';
import { mountChart, paintOf, pathPoints, pointer, tooltipEl, tooltipText } from './test-utils';

const labels = ['-2%', '-1%', '0%', '1%', '2%'];
const values = [3, -2, 5, null, 1];
const svg = () => document.querySelector('svg')!;
const bars = () => [...document.querySelectorAll<SVGRectElement>('rect[data-index]')];
const bar = (i: number) => document.querySelector<SVGRectElement>(`rect[data-index="${i}"]`)!;
const group = () => document.querySelector<HTMLElement>('[role="group"]')!;
const live = () => document.querySelector('[aria-live="polite"]')!;
const base = { labels, values, label: 'Test bars' };

/** Moves the pointer to the middle of a bar's column, at the bar's own height. */
function overBar(i: number) {
	const r = bar(i).getBoundingClientRect();
	pointer('pointermove', group(), r.left + r.width / 2, r.top + Math.max(1, r.height / 2));
}

describe('BarChart', () => {
	it('renders a rect per finite value at the measured width and height', async () => {
		mountChart(BarChart, { ...base, height: 200 }, 600);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('600');
		expect(svg().getAttribute('height')).toBe('200');
		expect(bars()).toHaveLength(4);
		expect(document.querySelector('rect[data-index="3"]')).toBeNull();
	});

	it('follows its container width', async () => {
		const { resize } = mountChart(BarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		const before = bar(0).getBoundingClientRect().width;
		resize(300);
		await expect.poll(() => svg().getAttribute('width')).toBe('300');
		expect(bar(0).getBoundingClientRect().width).toBeLessThan(before);
	});

	it('scales bars from a zero line that is drawn when a value is negative', async () => {
		mountChart(BarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(svg().querySelector('[data-zero]')).not.toBeNull();
		const zeroY = Number(svg().querySelector('[data-zero]')!.getAttribute('y1'));
		const y = (i: number) => Number(bar(i).getAttribute('y'));
		const h = (i: number) => Number(bar(i).getAttribute('height'));
		expect(y(0) + h(0)).toBeCloseTo(zeroY, 1);
		expect(y(1)).toBeCloseTo(zeroY, 1);
		expect(h(2)).toBeGreaterThan(h(0));
	});

	it('skips the zero line for all-positive data unless forced', async () => {
		const first = mountChart(BarChart, { ...base, values: [1, 2, 3, 4, 5] }, 600);
		await expect.poll(() => first.host.querySelectorAll('rect[data-index]').length).toBe(5);
		expect(first.host.querySelector('[data-zero]')).toBeNull();
		const forced = mountChart(BarChart, { ...base, values: [1, 2, 3, 4, 5], zeroLine: true }, 600);
		await expect.poll(() => forced.host.querySelector('[data-zero]')).not.toBeNull();
	});

	it('colours by sign with tokens only', async () => {
		mountChart(BarChart, { ...base, colorBy: 'sign' }, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(bar(0).style.fill).toBe('var(--chart-up)');
		expect(bar(1).style.fill).toBe('var(--chart-down)');
		expect(bar(2).style.fill).toBe('var(--chart-up)');
		const painted = [...svg().querySelectorAll('*')].flatMap(paintOf);
		for (const value of painted) expect(value).not.toMatch(/#|rgb\(/);
	});

	it('draws solid bars muted and emphasises the hovered one', async () => {
		mountChart(BarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(bar(2).style.fill).toBe('var(--ink-muted)');
		overBar(2);
		await expect.poll(() => bar(2).style.fill).toBe('var(--ink)');
		expect(bar(0).style.fill).toBe('var(--ink-muted)');
	});

	it('draws an overlay through the bar centres and breaks it at nulls', async () => {
		mountChart(BarChart, { ...base, overlay: [1, 2, null, 4, 5], overlayLabel: 'Normal fit' }, 600);
		await expect.poll(() => document.querySelector('path[data-overlay]')).not.toBeNull();
		const d = document.querySelector('path[data-overlay]')!.getAttribute('d');
		expect(d).not.toContain('NaN');
		expect(d!.match(/M/g)).toHaveLength(2);
		const first = pathPoints(d)[0];
		const box = bar(0).getBoundingClientRect();
		const shift = svg().querySelectorAll('g')[1].getAttribute('transform')!;
		const left = Number(/translate\(([\d.]+)/.exec(shift)![1]);
		expect(svg().getBoundingClientRect().left + left + first.x).toBeCloseTo(
			box.left + box.width / 2,
			0
		);
	});

	it('has no overlay path without an overlay', async () => {
		mountChart(BarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(document.querySelector('path[data-overlay]')).toBeNull();
	});

	it('draws dashed marker lines with captions on one row while they fit', async () => {
		mountChart(
			BarChart,
			{
				...base,
				markers: [
					{ index: 1, label: 'VaR 95%' },
					{ index: 2, label: 'VaR 99%' }
				]
			},
			600
		);
		await expect.poll(() => document.querySelectorAll('[data-marker-line]').length).toBe(2);
		const line = document.querySelector('[data-marker-line="1"]')!;
		expect(line.getAttribute('stroke-dasharray')).toBeTruthy();
		const captions = [...svg().querySelectorAll('[data-marker]')];
		expect(captions.map((c) => c.textContent)).toEqual(['VaR 95%', 'VaR 99%']);
		expect(captions[0].getAttribute('y')).toBe(captions[1].getAttribute('y'));
		const barBox = bar(1).getBoundingClientRect();
		expect(line.getBoundingClientRect().left).toBeCloseTo(barBox.left + barBox.width / 2, 0);
	});

	it('stacks marker captions that would collide and makes room for them', async () => {
		const markers = [
			{ index: 1, label: 'VaR 95%' },
			{ index: 2, label: 'VaR 99%' }
		];
		const stacked = mountChart(BarChart, { ...base, markers }, 300);
		await expect.poll(() => stacked.host.querySelectorAll('[data-marker]').length).toBe(2);
		const [a, b] = [...stacked.host.querySelectorAll('[data-marker]')].map((c) =>
			Number(c.getAttribute('y'))
		);
		expect(Math.abs(a - b)).toBeGreaterThanOrEqual(14);
		const plainTop = mountChart(BarChart, base, 300);
		await expect.poll(() => plainTop.host.querySelectorAll('rect[data-index]').length).toBe(4);
		const topOf = (host: HTMLElement) =>
			host.querySelector('rect[data-index="2"]')!.getBoundingClientRect().top;
		expect(topOf(stacked.host) - stacked.host.getBoundingClientRect().top).toBeGreaterThan(
			topOf(plainTop.host) - plainTop.host.getBoundingClientRect().top
		);
	});

	it('ignores markers outside the data', async () => {
		mountChart(BarChart, { ...base, markers: [{ index: 99, label: 'Nope' }] }, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(document.querySelectorAll('[data-marker-line]')).toHaveLength(0);
	});

	it('shows the label and formatted value on hover, with the overlay value', async () => {
		mountChart(
			BarChart,
			{
				...base,
				overlay: [1, 2, 3, 4, 5],
				overlayLabel: 'Normal fit',
				format: (v: number) => `${v} days`
			},
			600
		);
		await expect.poll(() => bars().length).toBe(4);
		expect(tooltipEl()).toBeNull();
		overBar(2);
		await expect.poll(tooltipText).toContain('0%');
		expect(tooltipText()).toContain('5 days');
		expect(tooltipText()).toContain('Normal fit');
		expect(tooltipText()).toContain('3 days');
		group().dispatchEvent(new PointerEvent('pointerleave'));
		await expect.poll(tooltipEl).toBeNull();
	});

	it('shows a dash for a missing value', async () => {
		mountChart(BarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		// Bar 3 is null, so aim one column to the right of bar 2.
		const box = bar(2).getBoundingClientRect();
		const svgBox = svg().getBoundingClientRect();
		pointer('pointermove', group(), box.right + box.width * 0.6, svgBox.top + 40);
		await expect.poll(tooltipText).toContain('1%');
		expect(tooltipText()).toContain('\u2014');
	});

	it('is keyboard operable and announces values', async () => {
		mountChart(BarChart, { ...base, format: (v: number) => `${v} days` }, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(group().getAttribute('tabindex')).toBe('0');
		expect(group().getAttribute('aria-label')).toBe('Test bars');
		group().focus();
		await expect.poll(tooltipText).toContain('-2%');
		await userEvent.keyboard('{ArrowRight}{ArrowRight}');
		await expect.poll(tooltipText).toContain('0%');
		expect(tooltipText()).toContain('5 days');
		expect(live().textContent).toContain('0%: Value 5 days');
		await userEvent.keyboard('{End}');
		await expect.poll(tooltipText).toContain('2%');
		await userEvent.keyboard('{Home}');
		await expect.poll(tooltipText).toContain('-2%');
		await userEvent.keyboard('{Escape}');
		await expect.poll(tooltipEl).toBeNull();
	});

	it('thins x labels to fit and honours labelEvery', async () => {
		const many = Array.from({ length: 40 }, (_, i) => `bin ${i}`);
		const data = many.map((_, i) => i);
		const texts = (host: HTMLElement) =>
			[...host.querySelectorAll('text')].filter((t) => t.textContent?.startsWith('bin ')).length;
		const dense = mountChart(BarChart, { labels: many, values: data, label: 'Dense' }, 400);
		await expect.poll(() => dense.host.querySelectorAll('rect[data-index]').length).toBe(40);
		expect(texts(dense.host)).toBeGreaterThan(1);
		expect(texts(dense.host)).toBeLessThan(20);
		const every = mountChart(
			BarChart,
			{ labels: many, values: data, labelEvery: 10, label: 'Every' },
			400
		);
		await expect.poll(() => every.host.querySelectorAll('rect[data-index]').length).toBe(40);
		expect(texts(every.host)).toBe(4);
	});

	it('exposes the data as a screen-reader table', async () => {
		mountChart(BarChart, { ...base, overlay: [1, 2, 3, 4, 5], overlayLabel: 'Normal fit' }, 600);
		await expect.poll(() => bars().length).toBe(4);
		const table = document.querySelector('.sr-only > table')!;
		expect(table.querySelector('caption')!.textContent).toBe('Test bars');
		expect(table.querySelectorAll('tbody tr')).toHaveLength(5);
		expect([...table.querySelectorAll('thead th')].map((t) => t.textContent)).toEqual([
			'Bin',
			'Value',
			'Normal fit'
		]);
		const cells = [...table.querySelectorAll('tbody tr')[3].querySelectorAll('th, td')].map(
			(c) => c.textContent
		);
		expect(cells).toEqual(['1%', '\u2014', '4']);
	});

	it('renders without data', async () => {
		mountChart(BarChart, { labels: [], values: [], label: 'Empty' }, 300);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('300');
		expect(bars()).toHaveLength(0);
	});
});

describe('BarChart screen-reader table', () => {
	it('is hidden without widening the page', async () => {
		// Regression: a table with sr-only ignores its 1px width and keeps its natural width, which
		// pushed the whole document sideways. The table must sit inside a clipping wrapper.
		mountChart(BarChart, { labels: ['W'.repeat(400), 'b'], values: [1, 2], label: 'test' }, 320);
		const root = document.documentElement;
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
		expect(document.querySelector('.sr-only > table')).not.toBeNull();
	});
});
