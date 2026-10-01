import { describe, expect, it, vi } from 'vitest';
import type { ApiClient } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import { ProvidersStore } from './providers.svelte';
import {
	TIERED,
	TIERED_CATEGORIES,
	TIERED_ENDPOINTS,
	catalog,
	provider,
	response
} from '$lib/testing/provider-fixtures';

const deferred = <T>() => {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
	return { promise, resolve, reject };
};

function setup(
	options: { providers?: ReturnType<typeof provider>[]; query?: ApiClient['queryProvider'] } = {}
) {
	const providers = options.providers ?? [
		provider(),
		provider({ id: 'other', name: 'Other', key_env: 'OTHER_KEY', configured: false })
	];
	const api = {
		listProviders: vi.fn(async () => providers),
		getProviderCatalog: vi.fn(async (id: string) => catalog(providers.find((p) => p.id === id))),
		queryProvider: vi.fn(options.query ?? (async () => response()))
	};
	const store = new ProvidersStore(api as unknown as ApiClient);
	return { api, store };
}

async function open(
	store: ProvidersStore,
	providerId = 'alphavantage',
	endpointId: string | null = 'TIME_SERIES_DAILY'
) {
	await store.loadProviders();
	store.select(providerId, endpointId);
	await vi.waitFor(() => expect(store.catalogStatus).toBe('ready'));
}

describe('ProvidersStore: nothing is fetched until asked', () => {
	it('loads the list and the catalog on selection, and never queries the provider', async () => {
		const { api, store } = setup();
		await open(store);
		expect(api.listProviders).toHaveBeenCalledOnce();
		expect(api.getProviderCatalog).toHaveBeenCalledWith('alphavantage');
		expect(api.queryProvider).not.toHaveBeenCalled();
		expect(store.endpoint?.id).toBe('TIME_SERIES_DAILY');
		expect(store.result).toBeNull();
	});

	it('seeds the form from the first documentation example without fetching, and applying another example does not fetch either', async () => {
		const { api, store } = setup();
		await open(store, 'alphavantage', 'TIME_SERIES_INTRADAY');
		expect(store.values).toEqual({ symbol: 'IBM', interval: '5min' });
		store.applyExample(1);
		expect(store.values).toEqual({ symbol: 'IBM', interval: '5min', month: '2009-01' });
		expect(api.queryProvider).not.toHaveBeenCalled();
	});

	it('loads each catalog once per provider', async () => {
		const { api, store } = setup();
		await open(store);
		store.select('other', null);
		await vi.waitFor(() => expect(store.catalogStatus).toBe('ready'));
		store.select('alphavantage', 'SMA');
		expect(api.getProviderCatalog).toHaveBeenCalledTimes(2);
	});
});

describe('ProvidersStore: fetching', () => {
	it('sends the trimmed parameters without blanks, then keeps the response and refreshes the request count', async () => {
		const { api, store } = setup();
		await open(store);
		store.setValue('symbol', ' IBM ');
		store.setValue('outputsize', '');
		await store.fetch();
		expect(api.queryProvider).toHaveBeenCalledWith(
			'alphavantage',
			{ endpoint: 'TIME_SERIES_DAILY', params: { symbol: 'IBM' }, refresh: false },
			expect.any(Object)
		);
		expect(store.queryStatus).toBe('ready');
		expect(store.result?.status).toBe('ok');
		await vi.waitFor(() => expect(api.listProviders).toHaveBeenCalledTimes(2));
	});

	it('passes refresh only for fetchFresh', async () => {
		const { api, store } = setup();
		await open(store);
		await store.fetchFresh();
		expect(api.queryProvider.mock.calls[0][1]).toMatchObject({ refresh: true });
	});

	it('does nothing while the form is invalid, and says why', async () => {
		const { api, store } = setup();
		await open(store);
		store.setValue('symbol', '');
		expect(store.canFetch).toBe(false);
		expect(store.blockedReason).toBe('Fix the highlighted fields first.');
		await store.fetch();
		expect(api.queryProvider).not.toHaveBeenCalled();
	});

	it('does nothing when the provider has no key, and names the variable to set', async () => {
		const { api, store } = setup();
		await open(store, 'other');
		expect(store.configured).toBe(false);
		expect(store.blockedReason).toBe('Set OTHER_KEY on the backend to fetch.');
		await store.fetch();
		expect(api.queryProvider).not.toHaveBeenCalled();
	});

	it('ignores a second fetch while one is in flight', async () => {
		const gate = deferred<ReturnType<typeof response>>();
		const { api, store } = setup({ query: () => gate.promise });
		await open(store);
		const first = store.fetch();
		await store.fetch();
		expect(api.queryProvider).toHaveBeenCalledOnce();
		expect(store.loading).toBe(true);
		gate.resolve(response());
		await first;
		expect(store.loading).toBe(false);
	});

	it('keeps a provider-side refusal as a response with its status, not as an error', async () => {
		const refusal = response({
			status: 'premium_required',
			message: 'premium',
			views: [],
			raw: null
		});
		const { store } = setup({ query: async () => refusal });
		await open(store);
		await store.fetch();
		expect(store.result?.status).toBe('premium_required');
		expect(store.queryError).toBeNull();
		expect(store.queryStatus).toBe('ready');
	});

	it('records a failed request as an error and no result', async () => {
		const { store } = setup({
			query: async () => Promise.reject(new ApiError('http', 'symbol is required', 422))
		});
		await open(store);
		await store.fetch();
		expect(store.queryStatus).toBe('error');
		expect(store.queryError?.message).toContain('symbol is required');
		expect(store.result).toBeNull();
	});
});

describe('ProvidersStore: results never outlive what produced them', () => {
	it('clears the result when another endpoint or provider is chosen', async () => {
		const { store } = setup();
		await open(store);
		await store.fetch();
		expect(store.result).not.toBeNull();
		store.select('alphavantage', 'SMA');
		expect(store.result).toBeNull();
		expect(store.queryStatus).toBe('idle');
		await store.fetch();
		store.select('other', null);
		expect(store.result).toBeNull();
	});

	it('keeps the result when only the same selection is re-applied', async () => {
		const { store } = setup();
		await open(store);
		await store.fetch();
		store.select('alphavantage', 'TIME_SERIES_DAILY');
		expect(store.result).not.toBeNull();
	});

	it('drops a response that arrives after the user moved to another endpoint', async () => {
		const gate = deferred<ReturnType<typeof response>>();
		const { store } = setup({ query: () => gate.promise });
		await open(store);
		const pending = store.fetch();
		store.select('alphavantage', 'SMA');
		gate.resolve(response({ title: 'stale' }));
		await pending;
		expect(store.result).toBeNull();
		expect(store.queryStatus).toBe('idle');
	});

	it('keeps a separate form per endpoint, and resets filters when the provider changes', async () => {
		const { store } = setup();
		await open(store);
		store.setValue('symbol', 'MSFT');
		store.select('alphavantage', 'SMA');
		expect(store.values.symbol).toBe('IBM');
		store.select('alphavantage', 'TIME_SERIES_DAILY');
		expect(store.values.symbol).toBe('MSFT');
		store.search = 'x';
		store.access = 'premium';
		store.select('other', null);
		expect([store.search, store.category, store.access]).toEqual(['', 'all', 'all']);
	});
});

describe('ProvidersStore: repeated parameters and filters', () => {
	it('adds and removes values of a repeated parameter and always leaves one slot', async () => {
		const { store } = setup();
		await open(store, 'alphavantage', 'ANALYTICS_FIXED_WINDOW');
		expect(store.values.RANGE).toEqual(['2023-07-01', '2023-08-31']);
		store.addEntry('RANGE');
		expect(store.values.RANGE).toEqual(['2023-07-01', '2023-08-31', '']);
		store.removeEntry('RANGE', 0);
		store.removeEntry('RANGE', 0);
		store.removeEntry('RANGE', 0);
		expect(store.values.RANGE).toEqual(['']);
	});

	it('filters the catalog and counts what each filter would show', async () => {
		const { store } = setup();
		await open(store);
		expect(store.counts).toEqual({ all: 5, free: 3, premium: 2 });
		store.access = 'premium';
		expect(store.endpoints.map((e) => e.id)).toEqual(['TIME_SERIES_INTRADAY', 'REALTIME_OPTIONS']);
		store.search = 'options';
		expect(store.endpoints.map((e) => e.id)).toEqual(['REALTIME_OPTIONS']);
	});

	it('reports a catalog failure and recovers on retry', async () => {
		const { api, store } = setup();
		api.getProviderCatalog.mockRejectedValueOnce(new ApiError('network', 'down'));
		await store.loadProviders();
		store.select('alphavantage', null);
		await vi.waitFor(() => expect(store.catalogStatus).toBe('error'));
		await store.loadCatalog('alphavantage');
		expect(store.catalogStatus).toBe('ready');
		expect(store.catalog?.endpoints).toHaveLength(5);
	});

	it('reports a failure to load the provider list', async () => {
		const { api, store } = setup();
		api.listProviders.mockRejectedValueOnce(new ApiError('network', 'down'));
		await store.loadProviders();
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('down');
	});
});

describe('ProvidersStore: a provider with plans', () => {
	function tieredStore() {
		const api = {
			listProviders: vi.fn(async () => [TIERED]),
			getProviderCatalog: vi.fn(async () => ({
				...catalog(TIERED, TIERED_ENDPOINTS),
				categories: TIERED_CATEGORIES
			})),
			queryProvider: vi.fn(async () => response())
		};
		return { api, store: new ProvidersStore(api as unknown as ApiClient) };
	}

	it('knows what each plan starts with and what one fetch costs', async () => {
		const { store } = tieredStore();
		await open(store, 'tiered', 'etfholdings');
		expect(store.plans.map((p) => [p.name, p.count, p.premium])).toEqual([
			['Free', 1, false],
			['Basic', 2, true],
			['Professional', 1, true]
		]);
		expect(store.requestCost).toBe(20);
		store.select('tiered', 'eod');
		expect(store.requestCost).toBe(1);
		store.select('tiered', null);
		expect(store.requestCost).toBe(1);
	});

	it('has no plans for a provider without tiers', async () => {
		const { store } = setup();
		await open(store);
		expect(store.plans).toEqual([]);
	});

	it('blocks a request above the documented limit before anything is sent', async () => {
		const { api, store } = tieredStore();
		await open(store, 'tiered', 'eod');
		store.setValue('limit', '5000');
		expect(store.errors.limit).toBe('limit must be at most 1000');
		expect(store.canFetch).toBe(false);
		await store.fetch();
		expect(api.queryProvider).not.toHaveBeenCalled();
	});
});
