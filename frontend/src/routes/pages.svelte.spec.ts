import type { Component } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import type { ApiClient } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { PerformanceMetrics, ResearchReport } from '$lib/api/contracts';
import { AppState } from '$lib/state/app.svelte';
import Harness from '$lib/testing/AppHarness.svelte';
import DatasetsPage from './+page.svelte';
import ResearchPage from './research/+page.svelte';

const client = (overrides: Partial<ApiClient>): ApiClient =>
	({
		listDatasets: vi.fn(async () => []),
		getBars: vi.fn(),
		runResearch: vi.fn(),
		...overrides
	}) as unknown as ApiClient;

const summary = (id: string, symbol: string) => ({
	id,
	symbol,
	timeframe: '5',
	path: `${symbol}/5.csv`,
	rows: 1234,
	size_bytes: 2048,
	modified: '',
	start: 1_700_000_000,
	end: 1_700_100_000,
	valid: true,
	error: null
});

async function mount(component: Component, api: ApiClient) {
	const app = new AppState(api);
	render(Harness, { app, component });
	return app;
}

describe('Datasets page', () => {
	it('shows an empty state and no rows when the backend has no data', async () => {
		const app = await mount(DatasetsPage, client({}));
		await app.datasets.load();
		await expect.element(page.getByText('No datasets yet')).toBeInTheDocument();
		expect(page.getByRole('table').elements()).toHaveLength(0);
		expect(document.body.textContent).not.toMatch(/BTC|ETH|BINANCE/);
	});

	it('lists exactly what the backend returned', async () => {
		const app = await mount(
			DatasetsPage,
			client({
				listDatasets: vi.fn(async () => [summary('a', 'BTCUSDT'), summary('b', 'ETHUSDT')])
			})
		);
		await app.datasets.load();
		await expect.element(page.getByText('BTCUSDT')).toBeInTheDocument();
		await expect.element(page.getByText('ETHUSDT')).toBeInTheDocument();
		expect(page.getByRole('link', { name: 'Explore' }).elements()).toHaveLength(2);
		expect(page.getByText('No datasets yet').elements()).toHaveLength(0);
	});

	it('explains a backend outage and retries', async () => {
		const listDatasets = vi
			.fn()
			.mockRejectedValueOnce(
				new ApiError('network', 'Cannot reach the backend. Check that `tvdata serve` is running.')
			)
			.mockResolvedValueOnce([]);
		const app = await mount(DatasetsPage, client({ listDatasets }));
		await app.datasets.load();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Cannot reach the backend');
		await page.getByRole('button', { name: 'Retry' }).click();
		await expect.element(page.getByText('No datasets yet')).toBeInTheDocument();
		expect(listDatasets).toHaveBeenCalledTimes(2);
	});

	it('flags invalid files without offering to open them', async () => {
		const bad = {
			...summary('c', 'BROKEN'),
			valid: false,
			error: 'missing required columns: volume'
		};
		const app = await mount(DatasetsPage, client({ listDatasets: vi.fn(async () => [bad]) }));
		await app.datasets.load();
		await expect.element(page.getByText('missing required columns: volume')).toBeInTheDocument();
		expect(page.getByRole('link', { name: 'Explore' }).elements()).toHaveLength(0);
	});
});

const metrics = (o: Partial<PerformanceMetrics> = {}): PerformanceMetrics => ({
	bars: 100,
	total_return_pct: 2,
	cagr_pct: 2,
	annualized_volatility_pct: 5,
	sharpe: 1,
	sortino: 1,
	max_drawdown_pct: -3,
	calmar: 1,
	trades: 5,
	win_rate_pct: 50,
	exposure_pct: 50,
	...o
});

function report(count: number): ResearchReport {
	return {
		schema_version: 1,
		metadata: {
			fee_bps_per_position_change: 5,
			periods_per_year: 252,
			strategy_count_per_asset: count,
			forward_validation: 'Fixed rules.'
		},
		assets: [
			{
				symbol: 'X',
				source: 'x.csv',
				rows: 10,
				start: '',
				end: '',
				quality: {} as never,
				benchmark: metrics(),
				benchmark_curve: [['2026-01-01T00:00:00+00:00', 1]]
			}
		],
		results: Array.from({ length: count }, (_, i) => ({
			id: `X-s${i}`,
			symbol: 'X',
			source: 'x.csv',
			family: i % 2 ? 'RSI mean reversion' : 'SMA crossover',
			name: `Strategy ${i}`,
			parameters: { fast: i },
			metrics: {
				full_sample: metrics(),
				in_sample: metrics(),
				forward: metrics({ sharpe: i / count })
			},
			forward_folds: [],
			equity_curve: [
				['2026-01-01T00:00:00+00:00', 1],
				['2026-01-02T00:00:00+00:00', 1 + i / 1000]
			],
			benchmark_curve: [['2026-01-01T00:00:00+00:00', 1]]
		})),
		model_notes: [],
		disclosures: ['Research only.']
	};
}

describe('Research page', () => {
	it('is empty until a run completes, and cannot run without a dataset', async () => {
		const runResearch = vi.fn();
		const app = await mount(
			ResearchPage,
			client({ listDatasets: vi.fn(async () => [summary('a', 'BTCUSDT')]), runResearch })
		);
		await app.datasets.load();
		await expect.element(page.getByText('No research run yet')).toBeInTheDocument();
		expect(page.getByRole('table').elements()).toHaveLength(0);
		await expect.element(page.getByRole('button', { name: 'Run research' })).toBeDisabled();
		expect(runResearch).not.toHaveBeenCalled();
	});

	it('runs the selected datasets, then filters and sorts a large virtualised result set', async () => {
		const runResearch = vi.fn(async () => report(5000));
		const app = await mount(
			ResearchPage,
			client({ listDatasets: vi.fn(async () => [summary('a', 'BTCUSDT')]), runResearch })
		);
		await app.datasets.load();
		await page.getByRole('checkbox', { name: /BTCUSDT/ }).click();
		await page.getByRole('button', { name: 'Run research' }).click();
		await expect.element(page.getByText('5,000 strategies', { exact: true })).toBeInTheDocument();
		expect(runResearch).toHaveBeenCalledWith(
			{ dataset_ids: ['a'], fee_bps: 5, periods_per_year: 252 },
			expect.anything()
		);

		const rendered = () => document.querySelectorAll('[role="row"]').length;
		expect(rendered()).toBeLessThan(60); // 5,000 results, only the window is in the DOM

		// Nothing is ranked by performance until asked: the table opens sorted by trade count.
		expect(app.research.sortKey).toBe('forward.trades');
		// Sorting by forward Sharpe is a deliberate click: descending first, so the last strategy leads...
		await page.getByRole('button', { name: /Fwd · Sharpe/ }).click();
		expect(app.research.sortKey).toBe('forward.sharpe');
		await expect.element(page.getByRole('button', { name: 'Strategy 4999' })).toBeInTheDocument();
		// ...and a second click flips it to ascending.
		await page.getByRole('button', { name: /Fwd · Sharpe/ }).click();
		await expect
			.element(page.getByRole('button', { name: 'Strategy 0', exact: true }))
			.toBeInTheDocument();

		// Add a family filter through the shared builder and watch the count update.
		await page.getByRole('button', { name: 'Condition' }).click();
		expect(app.research.filter.children).toHaveLength(1);
		app.research.filterEditor.patch(app.research.filter.children[0].id, {
			field: 'family',
			op: 'contains',
			text: 'rsi'
		});
		await expect
			.element(page.getByTestId('filter-matched'))
			.toHaveTextContent('2,500 of 5,000 strategies');
		expect(app.research.order.length).toBe(2500);
	});

	it('shows the backend error message when the run is rejected', async () => {
		const runResearch = vi.fn(async () => {
			throw new ApiError('http', 'unknown dataset id: a', 422);
		});
		const app = await mount(
			ResearchPage,
			client({ listDatasets: vi.fn(async () => [summary('a', 'BTCUSDT')]), runResearch })
		);
		await app.datasets.load();
		await page.getByRole('checkbox', { name: /BTCUSDT/ }).click();
		await page.getByRole('button', { name: 'Run research' }).click();
		await expect.element(page.getByRole('alert')).toHaveTextContent('unknown dataset id: a');
		expect(page.getByText('No research run yet').elements()).toHaveLength(0);
	});
});
