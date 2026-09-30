import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page, userEvent } from 'vitest/browser';
import type { ApiClient } from '$lib/api/client';
import type { Bars } from '$lib/api/validate';
import { ExplorerStore } from '$lib/state/explorer.svelte';
import { SavedFilters } from '$lib/state/saved-filters.svelte';
import Harness from '$lib/testing/ExplorerHarness.svelte';

/** Deterministic random-walk bars for component tests only. */
function bars(n: number): Bars {
	let seed = 5;
	const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
	const c = {
		time: new Float64Array(n),
		open: new Float64Array(n),
		high: new Float64Array(n),
		low: new Float64Array(n),
		close: new Float64Array(n),
		volume: new Float64Array(n)
	};
	let price = 100;
	for (let i = 0; i < n; i++) {
		const open = price;
		price *= 1 + (rand() - 0.5) * 0.02;
		c.time[i] = 1_700_000_000 + i * 3600;
		c.open[i] = open;
		c.close[i] = price;
		c.high[i] = Math.max(open, price) * 1.001;
		c.low[i] = Math.min(open, price) * 0.999;
		c.volume[i] = 100 + rand() * 50;
	}
	return {
		id: 'local:t',
		symbol: 'TEST',
		timeframe: null,
		columns: c,
		length: n,
		totalRows: n,
		droppedRows: 0,
		duplicateRows: 0,
		quality: null,
		origin: 'local'
	};
}

function mount(n = 600) {
	const explorer = new ExplorerStore({} as ApiClient);
	explorer.openLocal(bars(n));
	const saved = new SavedFilters('test', null);
	render(Harness, { explorer, saved });
	return explorer;
}

describe('explorer building blocks', () => {
	it('draws the chart and updates the legend when the pointer moves', async () => {
		mount();
		const canvas = document.querySelector('canvas')!;
		await vi.waitFor(() => {
			const ctx = canvas.getContext('2d')!;
			const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
			expect(data.some((v, i) => i % 4 === 3 && v > 0)).toBe(true); // something was painted
		});
		const legend = document.querySelector('figcaption')!;
		const before = legend.textContent;
		const rect = canvas.getBoundingClientRect();
		canvas.dispatchEvent(
			new PointerEvent('pointermove', {
				clientX: rect.left + 100,
				clientY: rect.top + 60,
				bubbles: true
			})
		);
		await vi.waitFor(() => expect(legend.textContent).not.toBe(before));
	});

	it('adds an indicator from the searchable library and lets it be hidden and removed', async () => {
		const explorer = mount();
		await page.getByRole('button', { name: /^Add/ }).click();
		await userEvent.keyboard('relative strength');
		await page.getByRole('option', { name: /Relative Strength Index/ }).click();
		await expect
			.element(page.getByTestId('indicator-item'))
			.toHaveTextContent('Relative Strength Index');
		expect(explorer.chart.panes).toHaveLength(1);
		await page.getByRole('button', { name: 'Hide Relative Strength Index' }).click();
		expect(explorer.chart.panes).toHaveLength(0);
		await page.getByRole('button', { name: 'Remove Relative Strength Index' }).click();
		expect(explorer.indicators).toHaveLength(0);
	});

	it('applies a preset, updates the match count and warns about full-sample percentiles', async () => {
		const explorer = mount();
		await expect.element(page.getByTestId('filter-matched')).toHaveTextContent('600 of 600 bars');
		await page.getByRole('button', { name: /^Presets/ }).click();
		await userEvent.keyboard('close makes a 20-bar high');
		await page.getByRole('option', { name: 'Close makes a 20-bar high', exact: true }).click();
		await expect.element(page.getByTestId('filter-count')).toHaveTextContent('1 active');
		const matched = explorer.evaluation!.matched;
		expect(matched).toBeGreaterThan(0);
		expect(matched).toBeLessThan(600);
		await expect
			.element(page.getByTestId('filter-matched'))
			.toHaveTextContent(`${matched} of 600 bars`);
		await expect
			.element(page.getByTestId('filter-summary'))
			.toHaveTextContent('Close makes a new 20-bar high');
		expect(page.getByText('Full-sample percentile in use').elements()).toHaveLength(0);

		await page.getByRole('button', { name: /^Presets/ }).click();
		await userEvent.keyboard('volume in the top 10');
		await page.getByRole('option', { name: /Volume in the top 10%/ }).click();
		await expect.element(page.getByText('Full-sample percentile in use')).toBeInTheDocument();
	});

	it('edits a condition value and re-evaluates immediately', async () => {
		const explorer = mount();
		await page.getByRole('button', { name: 'Condition' }).click();
		const id = explorer.filter.children[0].id;
		explorer.filterEditor.patch(id, { field: 'close', op: 'gt', value: 0 });
		await expect.element(page.getByTestId('filter-matched')).toHaveTextContent('600 of 600 bars');
		const input = page.getByRole('spinbutton', { name: 'Value' });
		await input.fill('1000000');
		await expect.element(page.getByTestId('filter-matched')).toHaveTextContent('0 of 600 bars');
		await expect.element(page.getByText('No bars match the current filter.')).toBeInTheDocument();
		await page.getByRole('checkbox', { name: 'Enable condition' }).click();
		await expect.element(page.getByTestId('filter-matched')).toHaveTextContent('600 of 600 bars');
	});

	it('reports an unknown field on a loaded filter instead of silently matching everything', async () => {
		const explorer = mount();
		await page.getByRole('button', { name: 'Condition' }).click();
		explorer.filterEditor.patch(explorer.filter.children[0].id, {
			field: 'rsi(period=99999).value',
			op: 'gt',
			value: 50
		});
		await expect.element(page.getByRole('alert')).toHaveTextContent('Unknown numeric field');
		await expect.element(page.getByTestId('filter-matched')).toHaveTextContent('0 of 600 bars');
	});

	it('keeps the matches table virtualised for very large match sets', async () => {
		const explorer = mount(20_000);
		explorer.filterEditor.add(explorer.filter.id, {
			type: 'condition',
			id: 'c1',
			enabled: true,
			field: 'close',
			op: 'gt',
			value: 0,
			value2: 0,
			rhs: null,
			text: ''
		});
		await expect.element(page.getByText('Time (UTC)')).toBeInTheDocument();
		expect(explorer.matches.length).toBe(20_000);
		const table = page.getByRole('table', { name: 'Bars matching the filter' }).element();
		expect(table.querySelectorAll('button').length).toBeLessThan(40);
	});

	it('validates event-study horizons without losing the last good value', async () => {
		const explorer = mount();
		explorer.filterEditor.add(explorer.filter.id, {
			type: 'condition',
			id: 'c1',
			enabled: true,
			field: 'close',
			op: 'gt',
			value: 0,
			value2: 0,
			rhs: null,
			text: ''
		});
		const input = page.getByRole('textbox', { name: 'Horizons (bars)' });
		await input.fill('2, 4');
		expect(explorer.horizons).toEqual([2, 4]);
		await input.fill('abc');
		await expect.element(page.getByRole('alert').first()).toHaveTextContent('whole numbers');
		expect(explorer.horizons).toEqual([2, 4]);
	});
});
