import { describe, expect, it, vi } from 'vitest';
import { createApiClient, extractDetail } from './client';
import { ApiError } from './errors';
import { parseBars, parseDatasetList, parseResearch } from './validate';

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const bars = (overrides: Record<string, unknown> = {}) => ({
	id: 'abc',
	symbol: 'BINANCE_BTCUSDT',
	timeframe: '5',
	rows: 3,
	total_rows: 3,
	dropped_rows: 0,
	duplicate_rows_collapsed: 0,
	columns: {
		time: [100, 160, 220],
		open: [1, 2, 3],
		high: [2, 3, 4],
		low: [0.5, 1, 2],
		close: [1.5, 2.5, 3.5],
		volume: [10, null, 30]
	},
	quality: null,
	...overrides
});

const metrics = { bars: 10, trades: 2, sharpe: null, total_return_pct: 1.2 };
const result = (id: string) => ({
	id,
	symbol: 'X',
	source: 'x.csv',
	family: 'SMA crossover',
	name: 'SMA 5/20',
	parameters: { fast: 5, slow: 20 },
	metrics: { full_sample: metrics, in_sample: metrics, forward: metrics },
	forward_folds: [{ start: 'a', end: 'b', metrics }],
	equity_curve: [['2026-01-01T00:00:00+05:30', 1]],
	benchmark_curve: [['2026-01-01T00:00:00+05:30', 1]]
});
const report = (results = [result('X-sma-5-20')]) => ({
	schema_version: 1,
	metadata: {
		fee_bps_per_position_change: 5,
		periods_per_year: 252,
		strategy_count_per_asset: 1,
		forward_validation: ''
	},
	assets: [{ symbol: 'X', benchmark: metrics, benchmark_curve: [['t', 1]] }],
	results,
	model_notes: [],
	disclosures: ['x']
});

describe('parseDatasetList', () => {
	it('accepts an empty listing without inventing entries', () => {
		expect(parseDatasetList({ datasets: [] }).datasets).toEqual([]);
	});

	it('rejects a malformed entry with a precise path', () => {
		expect(() => parseDatasetList({ datasets: [{ id: 'a' }] })).toThrow(/datasets\[0\]\.symbol/);
		expect(() => parseDatasetList({})).toThrow(ApiError);
	});
});

describe('parseBars', () => {
	it('builds typed columns and maps null to NaN', () => {
		const parsed = parseBars(bars());
		expect(parsed.columns.time).toBeInstanceOf(Float64Array);
		expect(parsed.length).toBe(3);
		expect(parsed.columns.volume[1]).toBeNaN();
		expect(parsed.origin).toBe('backend');
	});

	it.each([
		[
			'mismatched column length',
			bars({ columns: { ...bars().columns, close: [1] } }),
			/columns\.close/
		],
		[
			'unsorted time axis',
			bars({ columns: { ...bars().columns, time: [100, 100, 220] } }),
			/strictly increasing/
		],
		[
			'non-numeric value',
			bars({ columns: { ...bars().columns, open: [1, 'x', 3] } }),
			/columns\.open\[1\]/
		],
		['missing column', bars({ columns: { time: [1] } }), /columns\.open/]
	])('rejects %s', (_, payload, message) => {
		expect(() => parseBars(payload)).toThrow(message);
	});
});

describe('parseResearch', () => {
	it('accepts a valid report and defaults model_notes', () => {
		const { model_notes: _omit, ...withoutNotes } = report();
		void _omit;
		expect(parseResearch(withoutNotes).model_notes).toEqual([]);
	});

	it('rejects unsupported schema versions and duplicate ids', () => {
		expect(() => parseResearch({ ...report(), schema_version: 2 })).toThrow(/schema_version/);
		expect(() => parseResearch(report([result('a'), result('a')]))).toThrow(/unique/);
	});
});

describe('extractDetail', () => {
	it('reads FastAPI string and validation-list details', () => {
		expect(extractDetail({ detail: 'Unknown dataset' })).toBe('Unknown dataset');
		expect(
			extractDetail({ detail: [{ loc: ['body', 'fee_bps'], msg: 'Input should be <= 10000' }] })
		).toBe('fee_bps: Input should be <= 10000');
		expect(extractDetail('nope')).toBeNull();
	});
});

describe('api client', () => {
	it('lists datasets and returns an empty array for an empty backend', async () => {
		const fetch = vi.fn(async () => json({ datasets: [] }));
		expect(await createApiClient({ fetch }).listDatasets()).toEqual([]);
		expect(fetch).toHaveBeenCalledWith('/api/datasets', expect.anything());
	});

	it('url-encodes dataset ids and passes the limit', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json(bars()));
		await createApiClient({ fetch }).getBars('a/b c', { limit: 500.9 });
		expect(fetch.mock.calls[0][0]).toBe('/api/datasets/a%2Fb%20c/bars?limit=500');
	});

	it('surfaces backend detail for HTTP errors without retrying client faults', async () => {
		const fetch = vi.fn(async () => json({ detail: 'Unknown dataset id' }, 404));
		const error = await createApiClient({ fetch })
			.getBars('x')
			.catch((e) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect(error).toMatchObject({
			kind: 'http',
			status: 404,
			message: 'Unknown dataset id',
			retryable: false
		});
		expect(fetch).toHaveBeenCalledTimes(1);
	});

	it('retries idempotent GETs on 5xx and network faults, then succeeds', async () => {
		const fetch = vi
			.fn<typeof globalThis.fetch>()
			.mockRejectedValueOnce(new TypeError('Failed to fetch'))
			.mockResolvedValueOnce(json({ detail: 'boom' }, 503))
			.mockResolvedValueOnce(json({ datasets: [] }));
		const client = createApiClient({ fetch, retryDelayMs: 1 });
		expect(await client.listDatasets()).toEqual([]);
		expect(fetch).toHaveBeenCalledTimes(3);
	});

	it('gives up with a network error after the retry budget', async () => {
		const fetch = vi.fn(async () => {
			throw new TypeError('Failed to fetch');
		});
		const error = await createApiClient({ fetch, retries: 1, retryDelayMs: 1 })
			.listDatasets()
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'network', retryable: true });
		expect(fetch).toHaveBeenCalledTimes(2);
	});

	it('never retries the research POST', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json({ detail: 'busy' }, 503));
		const error = await createApiClient({ fetch, retryDelayMs: 1 })
			.runResearch({ dataset_ids: ['a'], fee_bps: 5, periods_per_year: 252 })
			.catch((e) => e);
		expect(error.status).toBe(503);
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST' });
	});

	it('reports a caller abort distinctly from a network failure', async () => {
		const controller = new AbortController();
		const fetch = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
			controller.abort();
			throw new DOMException('aborted', 'AbortError');
			void init;
		});
		const error = await createApiClient({ fetch })
			.listDatasets({ signal: controller.signal })
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'aborted' });
	});

	it('flags non-JSON success bodies and HTML proxy errors', async () => {
		const html = vi.fn(async () => new Response('<html>Bad gateway</html>', { status: 502 }));
		const error = await createApiClient({ fetch: html, retries: 0 })
			.listDatasets()
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'http', status: 502 });
		const garbage = vi.fn(async () => new Response('not json', { status: 200 }));
		await expect(createApiClient({ fetch: garbage }).listDatasets()).rejects.toMatchObject({
			kind: 'contract'
		});
	});

	it('rejects a contract-breaking payload from a 200 response', async () => {
		const fetch = vi.fn(async () => json(bars({ columns: { ...bars().columns, close: [1] } })));
		await expect(createApiClient({ fetch }).getBars('x')).rejects.toMatchObject({
			kind: 'contract'
		});
	});
});
