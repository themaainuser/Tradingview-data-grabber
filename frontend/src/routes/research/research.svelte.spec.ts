import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import Research from './+page.svelte';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/research') } }));

const summary = {
	id: 'abc',
	symbol: 'BINANCE:BTCUSDT',
	timeframe: '60',
	path: 'BINANCE_BTCUSDT/60.csv',
	rows: 1000,
	size_bytes: 1,
	modified: '2026-09-29T12:00:28Z',
	start: 1,
	end: 2,
	valid: true,
	error: null
};

const metrics = { bars: 100, trades: 12, sharpe: 0.5, total_return_pct: 1.2 };
const result = (id: string, name: string) => ({
	id,
	symbol: 'BINANCE:BTCUSDT-60',
	source: '60.csv',
	family: 'SMA crossover',
	name,
	parameters: { fast: 5, slow: 20 },
	metrics: { full_sample: metrics, in_sample: metrics, forward: metrics },
	forward_folds: [{ start: 'a', end: 'b', metrics }],
	equity_curve: [['2026-01-01T00:00:00+05:30', 1]],
	benchmark_curve: [['2026-01-01T00:00:00+05:30', 1]]
});

function report(sealed?: { dataset_id: string; excluded_bars: number }[]) {
	return {
		schema_version: 1,
		metadata: {
			fee_bps_per_position_change: 5,
			periods_per_year: 252,
			strategy_count_per_asset: 2,
			forward_validation: 'Fixed rules on forward folds.',
			...(sealed ? { sealed_holdouts: sealed } : {})
		},
		assets: [
			{
				symbol: 'BINANCE:BTCUSDT-60',
				benchmark: metrics,
				benchmark_curve: [['2026-01-01T00:00:00+05:30', 1]]
			}
		],
		results: [result('sma-5-20', 'SMA 5/20'), result('sma-10-20', 'SMA 10/20')],
		model_notes: [],
		disclosures: ['Research only.']
	};
}

afterEach(() => {
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

const mount = async () => {
	await page.viewport(1440, 900);
	render(InApp, { page: Research });
};

describe('Research page', () => {
	it('points at the Verdict page and says why the table is not sorted by Sharpe', async () => {
		stubBackend({ '/api/datasets': () => json({ datasets: [summary] }) });
		await mount();
		const note = page.getByTestId('verdict-pointer');
		await expect.element(note).toHaveTextContent('opens sorted by trade count');
		await expect.element(note).toHaveTextContent('fills at the signal bar');
		await expect
			.element(page.getByRole('link', { name: 'Verdict page' }))
			.toHaveAttribute('href', '/verdict');
	});

	it('tells the user when sealed bars were left out of a run', async () => {
		stubBackend({
			'/api/datasets': () => json({ datasets: [summary] }),
			'/api/research/run': () => json(report([{ dataset_id: 'abc', excluded_bars: 200 }]))
		});
		await mount();
		await page.getByRole('checkbox', { name: /BTCUSDT/ }).click();
		await page.getByRole('button', { name: 'Run research' }).click();
		await expect
			.element(page.getByTestId('sealed-note'))
			.toHaveTextContent('sealed on the Verdict page');
		await expect.element(page.getByTestId('sealed-note')).toHaveTextContent('200 bars');
	});

	it('shows no sealed note when nothing is sealed', async () => {
		stubBackend({
			'/api/datasets': () => json({ datasets: [summary] }),
			'/api/research/run': () => json(report())
		});
		await mount();
		await page.getByRole('checkbox', { name: /BTCUSDT/ }).click();
		await page.getByRole('button', { name: 'Run research' }).click();
		await expect.element(page.getByText('2 strategies', { exact: true })).toBeInTheDocument();
		expect(document.querySelector('[data-testid="sealed-note"]')).toBeNull();
	});
});
