import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import { goto } from '$app/navigation';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import {
	ALL_VIEWS,
	TIERED,
	TIERED_CATEGORIES,
	TIERED_ENDPOINTS,
	catalog,
	failure,
	provider,
	response
} from '$lib/testing/provider-fixtures';
import Providers from './[[provider]]/[[endpoint]]/+page.svelte';

const route = vi.hoisted(() => ({
	page: {
		url: new URL('http://localhost/providers'),
		params: { provider: undefined as string | undefined, endpoint: undefined as string | undefined }
	}
}));
vi.mock('$app/state', () => route);
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

const keyed = provider();
const unkeyed = provider({
	id: 'other',
	name: 'Other Data',
	key_env: 'OTHER_KEY',
	configured: false,
	endpoint_count: 5,
	premium_count: 2
});

function backend(
	query: () => Response | Promise<Response> = () => json(response()),
	providers = [keyed, unkeyed]
) {
	return stubBackend({
		'/api/datasets': () => json({ datasets: [] }),
		'/api/providers/alphavantage/catalog': () => json(catalog(keyed)),
		'/api/providers/other/catalog': () => json(catalog(unkeyed)),
		'/api/providers/alphavantage/query': query,
		'/api/providers/other/query': query,
		'/api/providers': () => json({ providers })
	});
}

const queries = (b: ReturnType<typeof backend>) =>
	b.fetch.mock.calls.filter(
		([url, init]) => String(url).endsWith('/query') && init?.method === 'POST'
	);

beforeEach(() => {
	route.page.params = { provider: 'alphavantage', endpoint: undefined };
});
afterEach(() => {
	vi.unstubAllGlobals();
	vi.mocked(goto).mockClear();
	document.body.innerHTML = '';
});

const mount = async (width = 1440) => {
	await page.viewport(width, 900);
	render(InApp, { page: Providers });
};
const fetchButton = () => page.getByRole('button', { name: 'Fetch data', exact: true });

describe('Providers page: browsing', () => {
	it('lists the provider with its key status and counts, and sends no query', async () => {
		const b = backend();
		await mount();
		await expect.element(page.getByRole('heading', { name: 'Alpha Vantage' })).toBeVisible();
		await expect.element(page.getByTestId('key-status')).toHaveTextContent('API key set');
		await expect.element(page.getByTestId('provider-counts')).toHaveTextContent('5 endpoints');
		await expect.element(page.getByTestId('provider-counts')).toHaveTextContent('2 premium');
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('5 endpoints');
		await expect.element(page.getByText('Choose an endpoint')).toBeVisible();
		expect(queries(b)).toHaveLength(0);
	});

	it('marks premium endpoints with the word Premium, not only a colour', async () => {
		backend();
		await mount();
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('5 endpoints');
		const rows = [...document.querySelectorAll<HTMLElement>('ul[aria-label="Endpoints"] button')];
		const premium = rows.filter((r) => r.dataset.premium === 'true');
		expect(rows).toHaveLength(5);
		expect(premium.map((r) => r.textContent)).toEqual([
			expect.stringContaining('TIME_SERIES_INTRADAY'),
			expect.stringContaining('REALTIME_OPTIONS')
		]);
		for (const row of premium)
			expect(row.querySelector('[data-testid="premium-badge"]')?.textContent).toContain('Premium');
		for (const row of rows.filter((r) => r.dataset.premium !== 'true'))
			expect(row.querySelector('[data-testid="premium-badge"]')).toBeNull();
	});

	it('filters to premium endpoints, searches, and offers a way back', async () => {
		backend();
		await mount();
		await page.getByRole('radio', { name: /Premium 2/ }).click();
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('2 endpoints');
		await page.getByLabelText('Search endpoints').fill('zzz');
		await expect.element(page.getByText('No endpoints match these filters.')).toBeVisible();
		await page.getByRole('button', { name: 'Clear filters' }).click();
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('5 endpoints');
	});

	it('navigates when an endpoint is chosen, without querying', async () => {
		const b = backend();
		await mount();
		await page.getByRole('button', { name: /Simple moving average/ }).click();
		expect(goto).toHaveBeenCalledWith('/providers/alphavantage/SMA', expect.any(Object));
		expect(queries(b)).toHaveLength(0);
	});

	it('lists every provider in the dropdown with its key status', async () => {
		backend();
		await mount();
		await page.getByRole('button', { name: 'Data provider' }).click();
		await expect
			.element(page.getByRole('option', { name: /Alpha Vantage/ }))
			.toHaveTextContent('Key set');
		await expect
			.element(page.getByRole('option', { name: /Other Data/ }))
			.toHaveTextContent('No key');
		await page.getByRole('option', { name: /Other Data/ }).click();
		expect(goto).toHaveBeenCalledWith('/providers/other', expect.any(Object));
	});

	it('redirects the bare address to the first provider', async () => {
		route.page.params = { provider: undefined, endpoint: undefined };
		backend();
		await mount();
		await vi.waitFor(() =>
			expect(goto).toHaveBeenCalledWith(
				'/providers/alphavantage',
				expect.objectContaining({ replaceState: true })
			)
		);
	});

	it('says so for an unknown provider and an unknown endpoint', async () => {
		route.page.params = { provider: 'nope', endpoint: undefined };
		backend();
		await mount();
		await expect.element(page.getByText('Provider not found')).toBeVisible();
		document.body.innerHTML = '';
		route.page.params = { provider: 'alphavantage', endpoint: 'NOT_AN_ENDPOINT' };
		await mount();
		await expect.element(page.getByText('Endpoint not found')).toBeVisible();
	});

	it('reports a backend that cannot be reached, with retry', async () => {
		stubBackend({
			'/api/datasets': () => json({ datasets: [] }),
			'/api/providers': () => new Response('down', { status: 503 })
		});
		await mount();
		await expect.element(page.getByText('Could not load the providers')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Retry' })).toBeVisible();
	});
});

describe('Providers page: premium highlighting', () => {
	it('calls out a premium endpoint in words', async () => {
		route.page.params = { provider: 'alphavantage', endpoint: 'TIME_SERIES_INTRADAY' };
		backend();
		await mount();
		await expect.element(page.getByTestId('premium-callout')).toHaveTextContent('Premium endpoint');
		await expect
			.element(page.getByTestId('premium-callout'))
			.toHaveTextContent('paid Alpha Vantage plan');
		await expect.element(page.getByTestId('endpoint-detail')).toHaveTextContent('Premium');
	});

	it('marks a premium option on a free endpoint, shows its note once, and flags the endpoint as free', async () => {
		route.page.params = { provider: 'alphavantage', endpoint: 'TIME_SERIES_DAILY' };
		backend();
		await mount();
		await expect
			.element(page.getByTestId('premium-options-callout'))
			.toHaveTextContent('Free endpoint with premium options');
		const badges = [...document.querySelectorAll('form [data-testid="premium-badge"]')];
		expect(badges.map((b) => b.textContent?.trim())).toEqual(['Premium option']);
		await expect
			.element(page.getByTestId('premium-note'))
			.toHaveTextContent('"full" outputsize is available to premium keys');
		expect(document.querySelector('[data-testid="premium-callout"]')).toBeNull();
		await expect
			.element(page.getByTestId('endpoint-detail').getByText('Free', { exact: true }))
			.toBeVisible();
	});

	it('does not show the parameters the server manages', async () => {
		route.page.params = { provider: 'alphavantage', endpoint: 'TIME_SERIES_DAILY' };
		backend();
		await mount();
		await expect.element(page.getByLabelText('symbol')).toBeVisible();
		expect(document.querySelector('[id^="param-TIME_SERIES_DAILY-datatype"]')).toBeNull();
		expect(document.querySelector('[id^="param-TIME_SERIES_DAILY-symbol"]')).not.toBeNull();
	});
});

describe('Providers page: fetching', () => {
	beforeEach(() => {
		route.page.params = { provider: 'alphavantage', endpoint: 'TIME_SERIES_DAILY' };
	});

	it('makes one query only when Fetch is pressed, sends only what was typed, and draws every view of the answer', async () => {
		const b = backend(() => json(response({ views: ALL_VIEWS() })));
		await mount();
		await expect.element(page.getByTestId('not-fetched')).toBeVisible();
		expect(queries(b)).toHaveLength(0);
		await page.getByLabelText('symbol').fill('MSFT');
		await fetchButton().click();
		await expect.element(page.getByTestId('result-meta')).toBeVisible();
		expect(queries(b)).toHaveLength(1);
		expect(JSON.parse(String(queries(b)[0][1]!.body))).toEqual({
			endpoint: 'TIME_SERIES_DAILY',
			params: { symbol: 'MSFT' },
			refresh: false
		});
		await expect.element(page.getByTestId('sent-params')).toHaveTextContent('symbol=IBM');
		for (const title of [
			'Summary',
			'Price history',
			'Biggest moves',
			'Articles',
			'Correlation',
			'Transcript'
		]) {
			await expect.element(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
		}
		expect(document.querySelectorAll('[data-testid="feed-item"]')).toHaveLength(2);
		expect(document.querySelector('[aria-label^="Candlestick chart"]')).not.toBeNull();
		expect(document.body.textContent).not.toMatch(/\bNaN\b|undefined/);
	});

	it('does not fetch, and says why, when the form is invalid', async () => {
		const b = backend();
		await mount();
		await page.getByLabelText('symbol').fill('');
		await expect.element(fetchButton()).toBeDisabled();
		await expect.element(page.getByTestId('field-error')).toHaveTextContent('symbol is required');
		await expect
			.element(page.getByTestId('fetch-help'))
			.toHaveTextContent('Fix the highlighted fields first.');
		expect(queries(b)).toHaveLength(0);
	});

	it('fetches again on request and says when the answer came from the cache', async () => {
		const b = backend(() => json(response({ cached: true })));
		await mount();
		await fetchButton().click();
		await expect.element(page.getByTestId('result-meta')).toHaveTextContent('served from cache');
		await page.getByRole('button', { name: /Fetch again/ }).click();
		await vi.waitFor(() => expect(queries(b)).toHaveLength(2));
		expect(JSON.parse(String(queries(b)[1][1]!.body)).refresh).toBe(true);
	});

	it('shows a premium refusal with its words and draws no data', async () => {
		const refusal = failure(
			'premium_required',
			'This is a premium endpoint. THE SAMPLE DATA IS ARTIFICIAL.'
		);
		backend(() => json(refusal));
		await mount();
		await fetchButton().click();
		const notice = page.getByTestId('status-notice');
		await expect.element(notice).toHaveTextContent('Premium access required');
		await expect
			.element(notice)
			.toHaveTextContent('Alpha Vantage says: This is a premium endpoint');
		await expect.element(notice).toHaveTextContent('not shown');
		expect(document.querySelectorAll('[id^="view-"]')).toHaveLength(0);
	});

	it.each([
		['rate_limited', 'Request limit reached'],
		['invalid_key', 'The API key was not accepted'],
		['upstream_error', 'The provider could not be reached'],
		['empty', 'No data returned']
	] as const)('shows %s as a notice and draws nothing', async (status, title) => {
		backend(() => json(failure(status, 'provider text')));
		await mount();
		await fetchButton().click();
		await expect.element(page.getByTestId('status-notice')).toHaveTextContent(title);
		await expect.element(page.getByTestId('provider-message')).toHaveTextContent('provider text');
		expect(document.querySelectorAll('[id^="view-"]')).toHaveLength(0);
	});

	it('shows a request failure as an error with the reason', async () => {
		backend(() => json({ detail: 'symbol is required' }, 422));
		await mount();
		await fetchButton().click();
		await expect.element(page.getByText('The request failed')).toBeVisible();
		await expect.element(page.getByRole('alert')).toHaveTextContent('symbol is required');
	});

	it('says what is being fetched while waiting', async () => {
		let release!: () => void;
		const gate = new Promise<void>((resolve) => (release = resolve));
		backend(async () => (await gate, json(response())));
		await mount();
		await fetchButton().click();
		await expect.element(page.getByText('Fetching from Alpha Vantage…')).toBeVisible();
		await expect.element(page.getByRole('button', { name: /Fetching/ })).toBeDisabled();
		release();
		await expect.element(page.getByTestId('result-meta')).toBeVisible();
	});
});

describe('Providers page: no API key', () => {
	it('explains how to set the key, disables Fetch with the reason, and never queries', async () => {
		route.page.params = { provider: 'other', endpoint: 'TIME_SERIES_DAILY' };
		const b = backend();
		await mount();
		await expect.element(page.getByTestId('key-status')).toHaveTextContent('No API key');
		await expect.element(page.getByTestId('key-help')).toHaveTextContent('OTHER_KEY');
		await expect.element(page.getByTestId('key-help')).toHaveTextContent('never sees it');
		await expect.element(fetchButton()).toBeDisabled();
		await expect
			.element(page.getByTestId('fetch-help'))
			.toHaveTextContent('Set OTHER_KEY on the backend to fetch.');
		expect(queries(b)).toHaveLength(0);
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('5 endpoints');
	});
});

describe('Providers page: narrow screens', () => {
	it('keeps the endpoint list and the form in one column without overflowing, before and after a fetch', async () => {
		route.page.params = { provider: 'alphavantage', endpoint: 'TIME_SERIES_DAILY' };
		backend(() => json(response({ views: ALL_VIEWS() })));
		await mount(390);
		await expect.element(page.getByLabelText('symbol')).toBeVisible();
		expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth + 1);
		await fetchButton().click();
		await expect.element(page.getByTestId('result-meta')).toBeVisible();
		expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth + 1);
	});
});

describe('Providers page: a provider with plans', () => {
	function tiered() {
		return stubBackend({
			'/api/datasets': () => json({ datasets: [] }),
			'/api/providers/tiered/catalog': () =>
				json({ ...catalog(TIERED, TIERED_ENDPOINTS), categories: TIERED_CATEGORIES }),
			'/api/providers/tiered/query': () => json(response()),
			'/api/providers': () => json({ providers: [TIERED] })
		});
	}

	beforeEach(() => {
		route.page.params = { provider: 'tiered', endpoint: undefined };
	});

	it('lays out the plans, what each one starts with, and marks the paid ones', async () => {
		tiered();
		await mount();
		await expect.element(page.getByTestId('plans')).toBeVisible();
		const cards = [...document.querySelectorAll<HTMLElement>('[data-testid="plans"] li')];
		expect(cards.map((c) => c.dataset.plan)).toEqual(['Free', 'Basic', 'Professional']);
		expect(cards.map((c) => c.dataset.premium)).toEqual([undefined, 'true', 'true']);
		expect(cards[1].textContent).toContain('2 endpoints start here');
		expect(cards[0].textContent).toContain('1 endpoint starts here');
		expect(cards[1].querySelector('[data-testid="premium-badge"]')?.textContent).toContain(
			'Premium'
		);
		expect(cards[0].querySelector('[data-testid="premium-badge"]')).toBeNull();
	});

	it('shows no plans for a provider that has none', async () => {
		route.page.params = { provider: 'alphavantage', endpoint: undefined };
		backend();
		await mount();
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('5 endpoints');
		expect(document.querySelector('[data-testid="plans"]')).toBeNull();
	});

	it('names the plan on every premium badge in the list and not on free endpoints', async () => {
		tiered();
		await mount();
		await expect.element(page.getByTestId('endpoint-count')).toHaveTextContent('4 endpoints');
		const rows = [...document.querySelectorAll<HTMLElement>('ul[aria-label="Endpoints"] button')];
		const labels = rows.map(
			(r) => r.querySelector('[data-testid="premium-badge"]')?.textContent?.trim() ?? null
		);
		expect(labels).toEqual([null, 'Premium · Basic', 'Premium · Basic', 'Premium · Professional']);
	});

	it('says which plan includes the open endpoint', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'commodities' };
		tiered();
		await mount();
		await expect
			.element(page.getByTestId('premium-callout-text'))
			.toHaveTextContent('included from the Professional plan');
		await expect
			.element(page.getByTestId('endpoint-detail'))
			.toHaveTextContent('Premium · Professional');
	});

	it('marks the premium choices of a parameter and says what a fetch costs', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'intraday' };
		tiered();
		await mount();
		await expect
			.element(page.getByTestId('premium-note'))
			.toHaveTextContent('below 15min need the Professional plan');
		await page.getByLabelText('interval').click();
		const options = [...document.querySelectorAll<HTMLElement>('[role="option"]')];
		const marked = options.filter((o) => o.querySelector('[data-testid="premium-badge"]'));
		expect(marked.map((o) => o.textContent?.trim())).toEqual([expect.stringContaining('1min')]);
		await expect.element(page.getByTestId('fetch-help')).toHaveTextContent('Uses one request');
	});

	it('warns that an ETF-style endpoint costs several requests, before and after fetching', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'etfholdings' };
		const b = tiered();
		await mount();
		await expect.element(page.getByTestId('fetch-help')).toHaveTextContent('Uses 20 requests');
		await fetchButton().click();
		await expect
			.element(page.getByRole('button', { name: /Fetch again \(uses 20 requests\)/ }))
			.toBeVisible();
		expect(queries(b as never)).toHaveLength(1);
	});

	it('takes an ISO-8601 timestamp for a datetime field and sends it as typed', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'eod' };
		const b = tiered();
		await mount();
		const date = page.getByLabelText('date', { exact: true });
		await date.fill('2020-05-21T00:00:00+0000');
		expect(document.querySelector('[data-testid="field-error"]')).toBeNull();
		await expect.element(fetchButton()).toBeEnabled();
		await fetchButton().click();
		await vi.waitFor(() => expect(queries(b as never)).toHaveLength(1));
		const body = JSON.parse(String(queries(b as never)[0][1]?.body));
		expect(body.params).toEqual({ symbols: 'AAPL', date: '2020-05-21T00:00:00+0000' });
	});

	it('explains a malformed timestamp beside the field and keeps Fetch off', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'eod' };
		const b = tiered();
		await mount();
		await page.getByLabelText('date', { exact: true }).fill('2020-05-21T25:00:00');
		await expect.element(page.getByTestId('field-error')).toHaveTextContent('ISO-8601 timestamp');
		await expect.element(fetchButton()).toBeDisabled();
		expect(queries(b as never)).toHaveLength(0);
	});

	it('stops an out-of-range limit before any request is sent', async () => {
		route.page.params = { provider: 'tiered', endpoint: 'eod' };
		const b = tiered();
		await mount();
		await page.getByLabelText('limit').fill('5000');
		await expect
			.element(page.getByTestId('field-error'))
			.toHaveTextContent('limit must be at most 1000');
		await expect.element(fetchButton()).toBeDisabled();
		expect(queries(b as never)).toHaveLength(0);
	});
});
