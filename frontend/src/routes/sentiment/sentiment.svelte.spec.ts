import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import Sentiment from './+page.svelte';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/sentiment') } }));

const DAY = 86_400;
const BANDS = [
	{ key: 'extreme_fear', label: 'Extreme fear', from: 0, to: 20 },
	{ key: 'fear', label: 'Fear', from: 20, to: 40 },
	{ key: 'neutral', label: 'Neutral', from: 40, to: 60 },
	{ key: 'greed', label: 'Greed', from: 60, to: 80 },
	{ key: 'extreme_greed', label: 'Extreme greed', from: 80, to: 100 }
];
const point = (score: number, band: string, label: string, time: number) => ({
	score,
	label,
	band,
	time
});

/** 120 daily readings: 10 (extreme fear) for the first 89 days, then `last` for the final 31. */
function payload(options: { last?: number; priced?: boolean; stale?: string | null } = {}) {
	const { last = 66, priced = true, stale = null } = options;
	const n = 120;
	const time = Array.from({ length: n }, (_, i) => 1_700_000_000 + i * DAY);
	const band = BANDS.find((b) => last >= b.from && last < b.to) ?? BANDS[4];
	const now = point(last, band.key, band.label, time[n - 1]);
	return {
		source: {
			name: 'CoinMarketCap',
			index: 'CMC Crypto Fear and Greed Index',
			url: 'https://coinmarketcap.com/charts/fear-and-greed-index/',
			endpoint: 'https://api.coinmarketcap.com/data-api/v3/fear-greed/chart',
			documented: false
		},
		fetched_at: time[n - 1] + 600,
		stale: stale !== null,
		stale_reason: stale,
		bands: BANDS,
		current: now,
		snapshots: {
			yesterday: point(68, 'greed', 'Greed', time[n - 2]),
			week_ago: null,
			month_ago: point(40, 'neutral', 'Neutral', time[n - 31]),
			year_high: point(82, 'extreme_greed', 'Extreme greed', time[5]),
			year_low: point(5, 'extreme_fear', 'Extreme fear', time[2])
		},
		points: {
			time,
			score: time.map((_, i) => (i < 89 ? 10 : last)),
			btc_price: time.map((_, i) => (priced ? 80_000 + i * 10 : null)),
			btc_volume: time.map(() => null)
		},
		total_points: n
	};
}

const backend = (sentiment: () => Response | Promise<Response>) =>
	stubBackend({
		'/api/datasets': () => json({ datasets: [] }),
		'/api/sentiment/fear-greed': sentiment
	});

afterEach(() => {
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

const mount = async () => {
	await page.viewport(1440, 900);
	render(InApp, { page: Sentiment });
};

describe('Fear & Greed page', () => {
	it('shows the reading the backend returned: gauge, comparisons, zones and summary', async () => {
		backend(() => json(payload({ last: 66 })));
		await mount();
		await expect.element(page.getByTestId('gauge-score')).toHaveTextContent('66');
		await expect.element(page.getByTestId('gauge-label')).toHaveTextContent('Greed');
		await expect
			.element(page.getByRole('img', { name: /gauge: 66 out of 100, Greed/ }))
			.toBeInTheDocument();
		expect(document.querySelectorAll('[data-testid^="snapshot-"]')).toHaveLength(6);
		await expect.element(page.getByTestId('snapshot-yesterday')).toHaveTextContent('68');
		await expect.element(page.getByTestId('snapshot-yesterday')).toHaveTextContent('\u22122 since');
		await expect.element(page.getByTestId('range-summary')).toBeInTheDocument();
		await expect.element(page.getByTestId('zone-bar')).toBeInTheDocument();
	});

	it('says so when a comparison day has no reading, instead of estimating one', async () => {
		backend(() => json(payload()));
		await mount();
		await expect
			.element(page.getByTestId('snapshot-week'))
			.toHaveTextContent('No reading for that day');
		const card = page.getByTestId('snapshot-week').element();
		expect(card.textContent).not.toMatch(/\d{2}-\d{2}/); // no date or score is invented
		expect(card.querySelector('[data-testid="meter-week"]')).toBeNull();
	});

	it('marks exactly the current band as active on the gauge', async () => {
		backend(() => json(payload({ last: 66 })));
		await mount();
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
		const active = document.querySelectorAll(
			'[data-testid="fear-greed-gauge"] path[data-active="true"]'
		);
		expect(active).toHaveLength(1);
		expect(active[0].getAttribute('data-band')).toBe('greed');
	});

	it('recomputes the zone shares when the range changes', async () => {
		backend(() => json(payload({ last: 50 })));
		await mount();
		await expect.element(page.getByTestId('zone-neutral')).toHaveTextContent('31 readings');
		await expect.element(page.getByTestId('zone-extreme_fear')).toHaveTextContent('60 readings');

		await page.getByRole('radio', { name: '30D' }).click();
		await expect
			.element(page.getByTestId('zone-neutral'))
			.toHaveTextContent('31 readings \u00b7 100%');
		await expect.element(page.getByTestId('zone-extreme_fear')).toHaveTextContent('0 readings');

		await page.getByRole('radio', { name: 'All' }).click();
		await expect.element(page.getByTestId('zone-extreme_fear')).toHaveTextContent('89 readings');
	});

	it('offers the Bitcoin price overlay only when the readings carry prices', async () => {
		backend(() => json(payload({ priced: false })));
		await mount();
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
		expect(document.getElementById('show-price')).toBeNull();
	});

	it('keeps the overlay switch when prices exist', async () => {
		backend(() => json(payload()));
		await mount();
		await expect.element(page.getByRole('switch', { name: 'Bitcoin price' })).toBeInTheDocument();
	});

	it('flags stale data and says when it was fetched', async () => {
		backend(() => json(payload({ stale: 'CoinMarketCap did not respond in time.' })));
		await mount();
		const notice = page.getByTestId('stale-notice');
		await expect.element(notice).toHaveTextContent('Showing the last fetched readings');
		await expect.element(notice).toHaveTextContent('CoinMarketCap did not respond in time.');
		await expect.element(notice).toHaveTextContent('UTC');
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
	});

	it('shows no stale notice for fresh data', async () => {
		backend(() => json(payload()));
		await mount();
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="stale-notice"]')).toBeNull();
	});

	it('shows the error and no reading at all when CoinMarketCap cannot be read, then recovers on retry', async () => {
		let calls = 0;
		backend(() =>
			++calls === 1
				? json({ detail: 'CoinMarketCap answered with HTTP 403.' }, 502)
				: json(payload())
		);
		await mount();
		await expect
			.element(page.getByText('CoinMarketCap answered with HTTP 403.'))
			.toBeInTheDocument();
		await expect.element(page.getByText('No reading to show')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="gauge-score"]')).toBeNull();
		expect(document.querySelector('[data-testid^="snapshot-"]')).toBeNull();
		expect(document.querySelector('[data-testid="range-summary"]')).toBeNull();

		await page.getByRole('button', { name: 'Retry' }).click();
		await expect.element(page.getByTestId('gauge-score')).toHaveTextContent('66');
		expect(document.body.textContent).not.toContain('No reading to show');
	});

	it('explains an out-of-date backend (404) instead of a bare "Not Found"', async () => {
		backend(() => json({ detail: 'Not Found' }, 404));
		await mount();
		await expect
			.element(page.getByText(/does not serve the Fear & Greed index/))
			.toBeInTheDocument();
		expect(document.querySelector('[data-testid="gauge-score"]')).toBeNull();
	});

	it('rejects a payload that breaks the contract rather than drawing wrong numbers', async () => {
		const broken = payload();
		broken.points.score = broken.points.score.slice(0, 10);
		backend(() => json(broken));
		await mount();
		await expect.element(page.getByText('No reading to show')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="gauge-score"]')).toBeNull();
	});

	it('refreshes on demand and credits the source with a safe external link', async () => {
		const { calls } = backend(() => json(payload()));
		await mount();
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
		const before = calls.filter((c) => c.startsWith('/api/sentiment')).length;
		await page.getByRole('button', { name: 'Refresh' }).click();
		await vi.waitFor(() =>
			expect(calls.filter((c) => c.startsWith('/api/sentiment')).length).toBe(before + 1)
		);
		const link = page.getByRole('link', { name: 'CMC Crypto Fear and Greed Index' });
		await expect
			.element(link)
			.toHaveAttribute('href', 'https://coinmarketcap.com/charts/fear-and-greed-index/');
		await expect.element(link).toHaveAttribute('rel', 'noreferrer noopener');
		await expect.element(link).toHaveAttribute('target', '_blank');
	});

	it('fits a phone-width screen without sideways page scroll', async () => {
		backend(() => json(payload()));
		await page.viewport(390, 844);
		render(InApp, { page: Sentiment });
		await expect.element(page.getByTestId('gauge-score')).toBeInTheDocument();
		const root = document.documentElement;
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
	});
});
