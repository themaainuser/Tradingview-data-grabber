import { describe, expect, it } from 'vitest';
import { userEvent } from 'vitest/browser';
import HBarChart from './HBarChart.svelte';
import { mountChart, paintOf, pointer, tooltipEl, tooltipText } from './test-utils';

const edges = [100, 110, 120, 130, 140];
const values = [10, 40, 20, 30];
const svg = () => document.querySelector('svg')!;
const bars = () => [...document.querySelectorAll<SVGRectElement>('rect[data-index]')];
const bar = (i: number) => document.querySelector<SVGRectElement>(`rect[data-index="${i}"]`)!;
const group = () => document.querySelector<HTMLElement>('[role="group"]')!;
const live = () => document.querySelector('[aria-live="polite"]')!;
const base = { edges, values, label: 'Test profile' };

function overBin(i: number) {
	const r = bar(i).getBoundingClientRect();
	pointer('pointermove', group(), r.left + 4, r.top + r.height / 2);
}

describe('HBarChart', () => {
	it('renders a bar per bin at the measured width and height', async () => {
		mountChart(HBarChart, { ...base, height: 300 }, 600);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('600');
		expect(svg().getAttribute('height')).toBe('300');
		expect(bars()).toHaveLength(4);
	});

	it('puts higher prices higher up and sizes bars by value', async () => {
		mountChart(HBarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		const y = (i: number) => Number(bar(i).getAttribute('y'));
		expect(y(3)).toBeLessThan(y(2));
		expect(y(1)).toBeLessThan(y(0));
		const w = (i: number) => Number(bar(i).getAttribute('width'));
		expect(w(1) / w(0)).toBeCloseTo(4, 3);
		expect(w(3) / w(2)).toBeCloseTo(1.5, 3);
	});

	it('follows its container width', async () => {
		const { resize } = mountChart(HBarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		const before = bar(1).getBoundingClientRect().width;
		resize(300);
		await expect.poll(() => svg().getAttribute('width')).toBe('300');
		expect(bar(1).getBoundingClientRect().width).toBeLessThan(before);
	});

	it('draws marker lines with captions in the gutter, skipping ones outside the range', async () => {
		mountChart(
			HBarChart,
			{
				...base,
				markers: [
					{ value: 125, label: 'POC' },
					{ value: 500, label: 'Off chart' }
				]
			},
			600
		);
		await expect.poll(() => document.querySelectorAll('[data-marker-line]').length).toBe(1);
		const caption = svg().querySelector('[data-caption="marker"]')!;
		expect(caption.textContent).toBe('POC');
		const line = svg().querySelector('[data-marker-line]')!;
		expect(Number(line.getAttribute('x2'))).toBeLessThan(Number(caption.getAttribute('x')));
		expect(svg().textContent).not.toContain('Off chart');
	});

	it('keeps captions of nearby markers from overlapping', async () => {
		mountChart(
			HBarChart,
			{
				...base,
				markers: [
					{ value: 125, label: 'POC' },
					{ value: 125.5, label: 'Last' }
				]
			},
			600
		);
		await expect.poll(() => document.querySelectorAll('[data-caption="marker"]').length).toBe(2);
		const ys = [...svg().querySelectorAll('[data-caption="marker"]')].map((c) =>
			Number(c.getAttribute('y'))
		);
		expect(Math.abs(ys[0] - ys[1])).toBeGreaterThanOrEqual(14 - 1e-6);
	});

	it('highlights the value area: ink inside, muted and dimmer outside, with a band and label', async () => {
		mountChart(HBarChart, { ...base, range: { low: 110, high: 130, label: 'Value area' } }, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(bar(1).style.fill).toBe('var(--ink)');
		expect(bar(2).style.fill).toBe('var(--ink)');
		expect(bar(0).style.fill).toBe('var(--ink-muted)');
		expect(bar(3).style.fill).toBe('var(--ink-muted)');
		expect(Number(bar(0).getAttribute('opacity'))).toBeLessThan(
			Number(bar(1).getAttribute('opacity'))
		);
		const band = svg().querySelector('[data-range]')!;
		expect(Number(band.getAttribute('height'))).toBeGreaterThan(0);
		expect(svg().querySelector('[data-caption="range"]')!.textContent).toBe('Value area');
	});

	it('paints with design tokens only', async () => {
		mountChart(
			HBarChart,
			{ ...base, range: { low: 110, high: 130 }, markers: [{ value: 125, label: 'POC' }] },
			600
		);
		await expect.poll(() => bars().length).toBe(4);
		const painted = [...svg().querySelectorAll('*')].flatMap(paintOf);
		expect(painted.length).toBeGreaterThan(5);
		for (const value of painted) expect(value).not.toMatch(/#|rgb\(/);
	});

	it('shows the price range, volume and share on hover', async () => {
		mountChart(
			HBarChart,
			{
				...base,
				priceFormat: (v: number) => `$${v}`,
				valueFormat: (v: number) => `${v} lots`
			},
			600
		);
		await expect.poll(() => bars().length).toBe(4);
		expect(tooltipEl()).toBeNull();
		overBin(1);
		await expect.poll(tooltipText).toContain('$110 \u2013 $120');
		expect(tooltipText()).toContain('40 lots');
		expect(tooltipText()).toContain('40.0%');
		expect(bar(1).style.fill).toBe('var(--ink)');
		group().dispatchEvent(new PointerEvent('pointerleave'));
		await expect.poll(tooltipEl).toBeNull();
	});

	it('is keyboard operable: starts at the busiest bin and moves by price', async () => {
		mountChart(HBarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		expect(group().getAttribute('tabindex')).toBe('0');
		group().focus();
		await expect.poll(tooltipText).toContain('110 \u2013 120');
		await userEvent.keyboard('{ArrowUp}');
		await expect.poll(tooltipText).toContain('120 \u2013 130');
		expect(live().textContent).toContain('120 \u2013 130');
		await userEvent.keyboard('{ArrowDown}{ArrowDown}');
		await expect.poll(tooltipText).toContain('100 \u2013 110');
		await userEvent.keyboard('{Home}');
		await expect.poll(tooltipText).toContain('130 \u2013 140');
		await userEvent.keyboard('{End}');
		await expect.poll(tooltipText).toContain('100 \u2013 110');
		await userEvent.keyboard('{Escape}');
		await expect.poll(tooltipEl).toBeNull();
	});

	it('exposes the data as a screen-reader table', async () => {
		mountChart(HBarChart, base, 600);
		await expect.poll(() => bars().length).toBe(4);
		const table = document.querySelector('.sr-only > table')!;
		expect(table.querySelectorAll('tbody tr')).toHaveLength(4);
		const row = [...table.querySelectorAll('tbody tr')[1].querySelectorAll('th, td')].map(
			(c) => c.textContent
		);
		expect(row).toEqual(['110 \u2013 120', '40', '40.0%']);
	});

	it('renders without data', async () => {
		mountChart(HBarChart, { edges: [], values: [], label: 'Empty' }, 300);
		await expect.poll(() => svg()?.getAttribute('width')).toBe('300');
		expect(bars()).toHaveLength(0);
	});
});

describe('HBarChart screen-reader table', () => {
	it('is hidden without widening the page', async () => {
		// Regression: see BarChart. Large edges make the price-range cells wide.
		mountChart(
			HBarChart,
			{
				edges: [1e300, 2e300, 3e300],
				values: [1, 2],
				priceFormat: (v: number) => 'W'.repeat(400) + v,
				label: 'test'
			},
			320
		);
		const root = document.documentElement;
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
		expect(document.querySelector('.sr-only > table')).not.toBeNull();
	});
});
