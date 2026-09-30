import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import Charts from './+page.svelte';

const route = vi.hoisted(() => ({
	page: {
		url: new URL('http://localhost/charts/abc'),
		params: { dataset: 'abc' as string | undefined }
	}
}));
vi.mock('$app/state', () => route);
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

const summary = (id: string, symbol: string) => ({
	id,
	symbol,
	timeframe: '60',
	path: `${symbol}/60.csv`,
	rows: 500,
	size_bytes: 1,
	modified: '2026-09-29T12:00:28Z',
	start: 1,
	end: 2,
	valid: true,
	error: null
});
const TWO = [summary('abc', 'BTC'), summary('def', 'ETH')];

const grid = (value: number | null) =>
	Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => value));
const seasonal = (n: number) => ({
	labels: Array.from({ length: n }, (_, i) => `L${i}`),
	mean_return_pct: Array.from({ length: n }, (_, i) => (i % 2 ? -0.02 : 0.03)),
	hit_rate_pct: Array.from({ length: n }, () => 52),
	count: Array.from({ length: n }, () => 20)
});

function charts(overrides: Record<string, unknown> = {}) {
	return {
		id: 'abc',
		symbol: 'BTC',
		timeframe: '60',
		bars: 500,
		interval_seconds: 3600,
		intraday: true,
		volume_profile: {
			edges: [100, 110, 120, 130],
			volume: [10, 30, 20],
			poc: 115,
			value_low: 100,
			value_high: 130,
			total_volume: 60
		},
		return_distribution: {
			edges: [-1, -0.5, 0, 0.5, 1],
			counts: [2, 10, 12, 3],
			normal: [3, 9, 11, 4],
			outliers: { below: 0, above: 2 },
			stats: {
				count: 27,
				mean_pct: 0.01,
				std_pct: 0.4,
				skew: 0.1,
				excess_kurtosis: 1.2,
				min_pct: -1.1,
				max_pct: 1.3,
				positive_pct: 52,
				var_95_pct: -0.7,
				cvar_95_pct: -0.9
			}
		},
		drawdown: {
			time: [1_700_000_000, 1_700_003_600, 1_700_007_200],
			drawdown_pct: [0, -1, -0.5],
			max_drawdown_pct: -1,
			peak_time: 1_700_000_000,
			trough_time: 1_700_003_600,
			recovered_time: null,
			current_drawdown_pct: -0.5,
			longest_underwater_bars: 2
		},
		rolling_volatility: {
			window: 30,
			time: [1_700_000_000, 1_700_003_600, 1_700_007_200],
			value_pct: [null, 0.2, 0.3]
		},
		activity: {
			hours: Array.from({ length: 24 }, (_, i) => i),
			weekdays: [0, 1, 2, 3, 4, 5, 6],
			metrics: { volume: grid(5), range_pct: grid(0.4), return_pct: grid(null) },
			counts: grid(3)
		},
		seasonality: { by_weekday: seasonal(7), by_hour: seasonal(24) },
		unavailable: {},
		...overrides
	};
}

let chartsResponse: () => Response;
let correlationResponse: (url: URL) => Response;
let datasets: ReturnType<typeof summary>[];
let backend: ReturnType<typeof stubBackend>;

beforeEach(() => {
	route.page.params.dataset = 'abc';
	datasets = TWO;
	chartsResponse = () => json(charts());
	correlationResponse = () =>
		json({
			labels: ['BTC-60', 'ETH-60'],
			matrix: [
				[1, 0.84],
				[0.84, 1]
			],
			observations: 999,
			start: 1_700_000_000,
			end: 1_700_086_400
		});
	backend = stubBackend({
		'/api/datasets': () => json({ datasets }),
		'/api/datasets/abc/charts': () => chartsResponse(),
		'/api/charts/correlation': (url) => correlationResponse(url)
	});
});
afterEach(() => {
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

const mount = async (width = 1440) => {
	await page.viewport(width, 900);
	render(InApp, { page: Charts });
};
const section = (id: string) => document.getElementById(id)!;

describe('Charts page', () => {
	it('renders every section from the backend response', async () => {
		await mount();
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		for (const id of [
			'volume-profile',
			'return-distribution',
			'drawdown',
			'rolling-volatility',
			'activity',
			'seasonality',
			'correlation'
		]) {
			expect(section(id), id).not.toBeNull();
		}
		await vi.waitFor(() => expect(section('correlation')).not.toBeNull());
		await expect.element(page.getByTestId('charts-summary')).toHaveTextContent('500');
		await expect.element(page.getByTestId('charts-summary')).toHaveTextContent('\u22121.00%'); // max drawdown
		expect(section('volume-profile').querySelectorAll('rect').length).toBeGreaterThanOrEqual(3);
		await expect.element(page.getByTestId('distribution-stats')).toHaveTextContent('VaR 95%');
		await expect.element(page.getByTestId('drawdown-stats')).toHaveTextContent('Not yet'); // not recovered
		expect(section('activity').querySelectorAll('[role="gridcell"]').length).toBe(168);
	});

	it('formats prices with two decimals', async () => {
		await mount();
		await expect.element(page.getByText(/POC 115\.00 .* value area 100\.00/)).toBeInTheDocument();
	});

	it('requests the charts for the dataset in the URL', async () => {
		await mount();
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		expect(backend.calls.filter((c) => c.startsWith('/api/datasets/abc/charts'))).toEqual([
			'/api/datasets/abc/charts?bins=60&window=30'
		]);
	});

	it('shows the backend reason in place of each section it could not compute', async () => {
		chartsResponse = () =>
			json(
				charts({
					return_distribution: null,
					drawdown: null,
					rolling_volatility: null,
					activity: null,
					seasonality: { by_weekday: null, by_hour: null },
					unavailable: {
						return_distribution: 'needs at least 30 returns; this dataset has 12',
						drawdown: 'needs at least two bars',
						rolling_volatility: 'needs more than 30 returns',
						activity: 'needs intraday bars; the median bar spacing is 86400 s',
						'seasonality.by_weekday': 'needs at least 30 returns'
					}
				})
			);
		await mount();
		await expect.element(page.getByText(/this dataset has 12/)).toBeInTheDocument();
		await expect
			.element(page.getByText(/needs intraday bars; the median bar spacing is 86400 s/))
			.toBeInTheDocument();
		await expect.element(page.getByText(/needs at least two bars/)).toBeInTheDocument();
		expect(document.querySelectorAll('[data-testid="unavailable"]')).toHaveLength(5);
		expect(section('activity').querySelector('[role="grid"]')).toBeNull();
		expect(section('drawdown').querySelector('[role="group"]')).toBeNull();
		// The volume profile never depends on optional analytics, so it is still drawn.
		expect(section('volume-profile').querySelectorAll('rect').length).toBeGreaterThan(0);
	});

	it('says which half of seasonality is unavailable when only one is', async () => {
		chartsResponse = () =>
			json(
				charts({
					seasonality: { by_weekday: seasonal(7), by_hour: null },
					unavailable: { 'seasonality.by_hour': 'needs intraday bars' }
				})
			);
		await mount();
		await expect
			.element(page.getByTestId('seasonality-hour'))
			.toHaveTextContent('Not available: needs intraday bars');
		await expect
			.element(page.getByTestId('seasonality-weekday'))
			.not.toHaveTextContent('Not available');
	});

	it('re-fetches with the chosen price bins and volatility window', async () => {
		await mount();
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		await page.getByRole('radio', { name: '100' }).first().click();
		await vi.waitFor(() =>
			expect(backend.calls).toContain('/api/datasets/abc/charts?bins=100&window=30')
		);
		await page
			.getByRole('group', { name: 'Window in bars' })
			.getByRole('radio', { name: '60' })
			.click();
		await vi.waitFor(() =>
			expect(backend.calls).toContain('/api/datasets/abc/charts?bins=100&window=60')
		);
	});

	it('switches the activity heatmap metric without another request', async () => {
		await mount();
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		const before = backend.calls.length;
		await page.getByRole('radio', { name: 'Return', exact: true }).click();
		await vi.waitFor(() =>
			expect(section('activity').textContent).toContain('close-to-close return')
		);
		expect(section('activity').textContent).not.toContain('high-to-low range');
		expect(backend.calls.length).toBe(before);
	});

	it('reports a failed load with a retry, and does not draw any chart', async () => {
		chartsResponse = () => json({ detail: 'dataset not found' }, 404);
		await mount();
		await expect.element(page.getByText('dataset not found')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="charts-summary"]')).toBeNull();
		expect(document.querySelector('svg[role="img"]')).toBeNull();
	});

	it('asks to choose a dataset when none is in the URL', async () => {
		route.page.params.dataset = undefined;
		await mount();
		await expect
			.element(page.getByText('Choose a dataset', { exact: true }).first())
			.toBeInTheDocument();
		expect(backend.calls.some((c) => c.includes('/charts'))).toBe(false);
	});

	it('explains that charts need backend captures when there are none', async () => {
		datasets = [];
		await mount();
		await expect.element(page.getByText('No backend datasets to chart')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="charts-summary"]')).toBeNull();
		expect(document.getElementById('correlation')).toBeNull();
	});

	it('hides correlation when there is only one dataset to compare', async () => {
		datasets = [TWO[0]];
		await mount();
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		expect(document.getElementById('correlation')).toBeNull();
	});
});

describe('Charts page: correlation', () => {
	it('waits for two datasets, then draws the matrix the backend computed', async () => {
		await mount();
		await expect.element(page.getByRole('checkbox', { name: /ETH/ })).toBeInTheDocument();
		await expect
			.element(page.getByText('Select at least two datasets to compare.'))
			.toBeInTheDocument();

		await page.getByRole('checkbox', { name: /BTC/ }).click();
		expect(backend.calls.some((c) => c.startsWith('/api/charts/correlation'))).toBe(false);
		await page.getByRole('checkbox', { name: /ETH/ }).click();

		await expect.element(page.getByTestId('correlation-result')).toBeInTheDocument();
		await expect
			.element(page.getByTestId('correlation-result'))
			.toHaveTextContent('999 overlapping returns');
		expect(backend.calls).toContain('/api/charts/correlation?ids=abc&ids=def');
		expect(section('correlation').querySelectorAll('[role="gridcell"]')).toHaveLength(4);
		await expect.element(page.getByRole('gridcell', { name: /0\.84/ }).first()).toBeInTheDocument();
	});

	it('shows the backend reason when the datasets share no timestamps, and no matrix', async () => {
		correlationResponse = () =>
			json(
				{
					detail: 'fewer than 3 overlapping returns; the selected datasets do not share timestamps'
				},
				422
			);
		await mount();
		await expect.element(page.getByRole('checkbox', { name: /ETH/ })).toBeInTheDocument();
		await page.getByRole('checkbox', { name: /BTC/ }).click();
		await page.getByRole('checkbox', { name: /ETH/ }).click();
		await expect
			.element(page.getByRole('alert').filter({ hasText: 'do not share timestamps' }))
			.toBeInTheDocument();
		expect(document.querySelector('[data-testid="correlation-result"]')).toBeNull();
	});

	it('returns to the prompt when the selection drops below two', async () => {
		await mount();
		await expect.element(page.getByRole('checkbox', { name: /ETH/ })).toBeInTheDocument();
		await page.getByRole('checkbox', { name: /BTC/ }).click();
		await page.getByRole('checkbox', { name: /ETH/ }).click();
		await expect.element(page.getByTestId('correlation-result')).toBeInTheDocument();
		await page.getByRole('checkbox', { name: /ETH/ }).click();
		await expect
			.element(page.getByText('Select at least two datasets to compare.'))
			.toBeInTheDocument();
		expect(document.querySelector('[data-testid="correlation-result"]')).toBeNull();
	});
});

describe('Charts page: layout', () => {
	it('fits a phone-width screen without sideways page scroll', async () => {
		await mount(390);
		await expect.element(page.getByTestId('charts-summary')).toBeInTheDocument();
		const root = document.documentElement;
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
	});
});
