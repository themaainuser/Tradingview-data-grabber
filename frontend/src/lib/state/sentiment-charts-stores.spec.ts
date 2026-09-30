import { describe, expect, it, vi } from 'vitest';
import type { ApiClient } from '$lib/api/client';
import type { ChartsResponse, CorrelationResponse, FearGreedResponse } from '$lib/api/contracts';
import { ApiError } from '$lib/api/errors';
import { ChartsStore, MAX_CORRELATION } from './charts.svelte';
import { SentimentStore } from './sentiment.svelte';

const DAY = 86_400;
const deferred = <T>() => {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
	return { promise, resolve, reject };
};

const BANDS: FearGreedResponse['bands'] = [
	{ key: 'extreme_fear', label: 'Extreme fear', from: 0, to: 20 },
	{ key: 'fear', label: 'Fear', from: 20, to: 40 },
	{ key: 'neutral', label: 'Neutral', from: 40, to: 60 },
	{ key: 'greed', label: 'Greed', from: 60, to: 80 },
	{ key: 'extreme_greed', label: 'Extreme greed', from: 80, to: 100 }
];

/** 120 daily readings: 10 (extreme fear) for the first 89 days, then 50 (neutral) for the last 31. */
function fearGreed(priced = true): FearGreedResponse {
	const n = 120;
	const time = Array.from({ length: n }, (_, i) => 1_700_000_000 + i * DAY);
	const score = time.map((_, i) => (i < 89 ? 10 : 50));
	const current = { score: 50, label: 'Neutral', band: 'neutral' as const, time: time[n - 1] };
	return {
		source: {
			name: 'CoinMarketCap',
			index: 'idx',
			url: 'https://example.test',
			endpoint: 'https://example.test/api',
			documented: false
		},
		fetched_at: time[n - 1],
		stale: false,
		stale_reason: null,
		bands: BANDS,
		current,
		snapshots: {
			yesterday: null,
			week_ago: null,
			month_ago: null,
			year_high: current,
			year_low: { ...current, score: 10, label: 'Extreme fear', band: 'extreme_fear' }
		},
		points: {
			time,
			score,
			btc_price: time.map((_, i) => (priced ? 1000 + i : null)),
			btc_volume: time.map(() => null)
		},
		total_points: n
	};
}

const api = (overrides: Partial<ApiClient>) => overrides as unknown as ApiClient;

describe('SentimentStore', () => {
	it('holds nothing until the backend answers, then exposes the readings', async () => {
		const getFearGreed = vi.fn(async () => fearGreed());
		const store = new SentimentStore(api({ getFearGreed }));
		expect(store.data).toBeNull();
		expect(store.view).toBeNull();
		expect(store.zones).toEqual([]);
		expect(store.summary).toBeNull();
		expect(store.hasPrice).toBe(false);
		await store.load();
		expect(store.status).toBe('ready');
		expect(store.error).toBeNull();
		expect(store.data?.current.score).toBe(50);
	});

	it('stays empty and reports the error when the first load fails, never inventing data', async () => {
		const store = new SentimentStore(
			api({
				getFearGreed: vi.fn(async () =>
					Promise.reject(new ApiError('http', 'CoinMarketCap answered with HTTP 403.', 502))
				)
			})
		);
		await store.load();
		expect(store.status).toBe('error');
		expect(store.error?.message).toContain('HTTP 403');
		expect(store.data).toBeNull();
	});

	it('keeps the previous readings on screen when a refresh fails', async () => {
		const getFearGreed = vi
			.fn()
			.mockResolvedValueOnce(fearGreed())
			.mockRejectedValueOnce(new ApiError('network', 'offline'));
		const store = new SentimentStore(api({ getFearGreed }));
		await store.load();
		const first = store.data;
		await store.load();
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('offline');
		expect(store.data).toBe(first);
	});

	it('explains a 404 as an out-of-date backend instead of "Not Found"', async () => {
		const store = new SentimentStore(
			api({
				getFearGreed: vi.fn(async () => Promise.reject(new ApiError('http', 'Not Found', 404)))
			})
		);
		await store.load();
		expect(store.error?.status).toBe(404);
		expect(store.error?.message).toMatch(/does not serve the Fear & Greed index/);
	});

	it('ignores a superseded request, including its abort', async () => {
		const first = deferred<FearGreedResponse>();
		const second = fearGreed();
		const getFearGreed = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce(second);
		const store = new SentimentStore(api({ getFearGreed }));
		const older = store.load();
		await store.load();
		expect(store.data).toBe(second);
		first.reject(new DOMException('aborted', 'AbortError'));
		await older;
		expect(store.data).toBe(second);
		expect(store.error).toBeNull();
		expect(store.status).toBe('ready');
	});

	it('ignores an older response that arrives after a newer one', async () => {
		const older = deferred<FearGreedResponse>();
		const newer = fearGreed();
		const getFearGreed = vi.fn().mockReturnValueOnce(older.promise).mockResolvedValueOnce(newer);
		const store = new SentimentStore(api({ getFearGreed }));
		const first = store.load();
		await store.load();
		older.resolve({ ...fearGreed(), fetched_at: 1 });
		await first;
		expect(store.data).toBe(newer);
		expect(store.data?.fetched_at).not.toBe(1);
	});

	it('derives the range window, zone shares and summary from the readings', async () => {
		const store = new SentimentStore(api({ getFearGreed: vi.fn(async () => fearGreed()) }));
		await store.load();

		store.range = '30d';
		expect(store.view?.time).toHaveLength(31);
		expect(store.zones.find((z) => z.key === 'neutral')).toMatchObject({ count: 31, share: 1 });
		expect(store.summary).toMatchObject({ count: 31, mean: 50, change: 0 });

		store.range = '90d'; // 91 readings: the last 30 days plus 60 earlier extreme-fear days
		expect(store.view?.score).toHaveLength(91);
		expect(store.zones.find((z) => z.key === 'extreme_fear')?.count).toBe(60);
		expect(store.summary?.change).toBe(40);
		expect(store.summary?.low.score).toBe(10);

		store.range = 'all';
		expect(store.view?.score).toHaveLength(120);
		expect(store.zones.reduce((sum, z) => sum + z.count, 0)).toBe(120);
		expect(store.view?.price[0]).toBe(1000);
		expect(store.hasPrice).toBe(true);
	});

	it('reports no price overlay when no reading in the range has a price', async () => {
		const store = new SentimentStore(api({ getFearGreed: vi.fn(async () => fearGreed(false)) }));
		await store.load();
		expect(store.hasPrice).toBe(false);
	});
});

const chartsResponse = (id = 'a', bins = 60): ChartsResponse => ({
	id,
	symbol: id.toUpperCase(),
	timeframe: '60',
	bars: 100,
	interval_seconds: 3600,
	intraday: true,
	volume_profile: {
		edges: Array.from({ length: bins + 1 }, (_, i) => i),
		volume: Array.from({ length: bins }, () => 1),
		poc: 1,
		value_low: 0,
		value_high: bins,
		total_volume: bins
	},
	return_distribution: null,
	drawdown: null,
	rolling_volatility: null,
	activity: null,
	seasonality: { by_weekday: null, by_hour: null },
	unavailable: {}
});

const matrix = (labels: string[]): CorrelationResponse => ({
	labels,
	matrix: labels.map((_, i) => labels.map((_, j) => (i === j ? 1 : 0.5))),
	observations: 50,
	start: 1,
	end: 2
});

describe('ChartsStore', () => {
	it('opens a dataset with the current bins and window', async () => {
		const getCharts = vi.fn(async (id: string) => chartsResponse(id));
		const store = new ChartsStore(api({ getCharts }));
		expect(store.charts).toBeNull();
		await store.open('a');
		expect(getCharts).toHaveBeenCalledWith('a', expect.objectContaining({ bins: 60, window: 30 }));
		expect(store.datasetId).toBe('a');
		expect(store.status).toBe('ready');
		expect(store.charts?.id).toBe('a');
	});

	it('lets a newer open supersede an older one that resolves later', async () => {
		const slow = deferred<ChartsResponse>();
		const getCharts = vi
			.fn()
			.mockReturnValueOnce(slow.promise)
			.mockResolvedValueOnce(chartsResponse('b'));
		const store = new ChartsStore(api({ getCharts }));
		const older = store.open('a');
		await store.open('b');
		slow.resolve(chartsResponse('a'));
		await older;
		expect(store.charts?.id).toBe('b');
		expect(store.datasetId).toBe('b');
	});

	it('re-fetches the open dataset when bins or window change, and does nothing without one', async () => {
		const getCharts = vi.fn(async (id: string) => chartsResponse(id));
		const store = new ChartsStore(api({ getCharts }));
		await store.setBins(100);
		expect(getCharts).not.toHaveBeenCalled();
		await store.open('a');
		await store.setBins(100);
		expect(getCharts).toHaveBeenLastCalledWith('a', expect.objectContaining({ bins: 100 }));
		await store.setWindow(60);
		expect(getCharts).toHaveBeenLastCalledWith(
			'a',
			expect.objectContaining({ bins: 100, window: 60 })
		);
		expect(getCharts).toHaveBeenCalledTimes(3);
	});

	it('reports a failure and keeps what was already loaded', async () => {
		const getCharts = vi
			.fn()
			.mockResolvedValueOnce(chartsResponse('a'))
			.mockRejectedValueOnce(new ApiError('http', 'dataset not found', 404));
		const store = new ChartsStore(api({ getCharts }));
		await store.open('a');
		await store.open('a');
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('dataset not found');
		expect(store.charts?.id).toBe('a');
	});

	it('needs two datasets before asking for a correlation, then drops it again below two', async () => {
		const getCorrelation = vi.fn(async (ids: readonly string[]) => matrix([...ids]));
		const store = new ChartsStore(api({ getCorrelation }));
		await store.toggleCorrelation('a');
		expect(getCorrelation).not.toHaveBeenCalled();
		expect(store.correlation).toBeNull();
		await store.toggleCorrelation('b');
		expect(getCorrelation).toHaveBeenCalledWith(['a', 'b'], expect.anything());
		expect(store.correlation?.labels).toEqual(['a', 'b']);
		expect(store.correlationStatus).toBe('ready');
		await store.toggleCorrelation('a');
		expect(store.correlation).toBeNull();
		expect(store.correlationStatus).toBe('idle');
		expect(store.correlationIds).toEqual(['b']);
	});

	it('discards the old matrix when a new selection fails, rather than showing a mismatched one', async () => {
		const getCorrelation = vi
			.fn()
			.mockResolvedValueOnce(matrix(['a', 'b']))
			.mockRejectedValueOnce(new ApiError('http', 'fewer than 3 overlapping returns', 422));
		const store = new ChartsStore(api({ getCorrelation }));
		await store.toggleCorrelation('a');
		await store.toggleCorrelation('b');
		expect(store.correlation).not.toBeNull();
		await store.toggleCorrelation('c');
		expect(store.correlation).toBeNull();
		expect(store.correlationStatus).toBe('error');
		expect(store.correlationError?.message).toBe('fewer than 3 overlapping returns');
	});

	it('caps the selection at the backend limit', async () => {
		const getCorrelation = vi.fn(async (ids: readonly string[]) => matrix([...ids]));
		const store = new ChartsStore(api({ getCorrelation }));
		for (let i = 0; i < MAX_CORRELATION + 3; i++) await store.toggleCorrelation(`d${i}`);
		expect(store.correlationIds).toHaveLength(MAX_CORRELATION);
		expect(store.correlationIds).not.toContain(`d${MAX_CORRELATION}`);
	});

	it('reset clears the dataset, charts and selection', async () => {
		const store = new ChartsStore(
			api({
				getCharts: vi.fn(async (id: string) => chartsResponse(id)),
				getCorrelation: vi.fn(async (ids: readonly string[]) => matrix([...ids]))
			})
		);
		await store.open('a');
		await store.toggleCorrelation('a');
		await store.toggleCorrelation('b');
		store.reset();
		expect(store.datasetId).toBeNull();
		expect(store.charts).toBeNull();
		expect(store.status).toBe('idle');
		expect(store.correlationIds).toEqual([]);
		expect(store.correlation).toBeNull();
	});
});
