import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';
import { ApiError } from './errors';
import { parseCharts, parseCorrelation, parseFearGreed } from './validate';

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const DAY = 86_400;
const point = (score: number, band: string, label: string, time = 1_790_000_000) => ({
	score,
	label,
	band,
	time
});

/** A valid Fear & Greed payload in the shape the backend returns; overrides replace top-level keys. */
const fearGreed = (overrides: Record<string, unknown> = {}) => ({
	source: {
		name: 'CoinMarketCap',
		index: 'CMC Crypto Fear and Greed Index',
		url: 'https://coinmarketcap.com/charts/fear-and-greed-index/',
		endpoint: 'https://api.coinmarketcap.com/data-api/v3/fear-greed/chart',
		documented: false
	},
	fetched_at: 1_790_000_100,
	stale: false,
	stale_reason: null,
	bands: [
		{ key: 'extreme_fear', label: 'Extreme fear', from: 0, to: 20 },
		{ key: 'fear', label: 'Fear', from: 20, to: 40 },
		{ key: 'neutral', label: 'Neutral', from: 40, to: 60 },
		{ key: 'greed', label: 'Greed', from: 60, to: 80 },
		{ key: 'extreme_greed', label: 'Extreme greed', from: 80, to: 100 }
	],
	current: point(66, 'greed', 'Greed'),
	snapshots: {
		yesterday: point(68, 'greed', 'Greed'),
		week_ago: null,
		month_ago: point(40, 'neutral', 'Neutral'),
		year_high: point(82, 'extreme_greed', 'Extreme greed'),
		year_low: point(5, 'extreme_fear', 'Extreme fear')
	},
	points: {
		time: [1_789_900_000, 1_789_900_000 + DAY, 1_789_900_000 + 2 * DAY],
		score: [60, 64, 66],
		btc_price: [80_000.5, null, 81_250],
		btc_volume: [1e9, 2e9, null]
	},
	total_points: 3,
	...overrides
});

describe('parseFearGreed', () => {
	it('accepts a valid payload, keeping nulls for missing snapshots, prices and volumes', () => {
		const parsed = parseFearGreed(fearGreed());
		expect(parsed.current.score).toBe(66);
		expect(parsed.snapshots.week_ago).toBeNull();
		expect(parsed.snapshots.year_low.band).toBe('extreme_fear');
		expect(parsed.points.btc_price).toEqual([80_000.5, null, 81_250]);
		expect(parsed.source.documented).toBe(false);
		expect(parsed.stale).toBe(false);
	});

	const bad: [string, (p: ReturnType<typeof fearGreed>) => unknown, RegExp][] = [
		['a non-object response', () => null, /response/],
		[
			'a column shorter than the time axis',
			(p) => ({ ...p, points: { ...p.points, score: [60, 64] } }),
			/points\.score/
		],
		[
			'a price column of the wrong length',
			(p) => ({ ...p, points: { ...p.points, btc_price: [1] } }),
			/points\.btc_price/
		],
		[
			'a time axis that is not increasing',
			(p) => ({ ...p, points: { ...p.points, time: [3, 2, 1] } }),
			/strictly increasing/
		],
		[
			'an empty history',
			(p) => ({ ...p, points: { time: [], score: [], btc_price: [], btc_volume: [] } }),
			/non-empty/
		],
		[
			'a score above 100',
			(p) => ({ ...p, points: { ...p.points, score: [60, 64, 101] } }),
			/0 to 100/
		],
		[
			'a fractional score',
			(p) => ({ ...p, points: { ...p.points, score: [60, 64.5, 66] } }),
			/whole number/
		],
		[
			'a NaN price',
			(p) => ({ ...p, points: { ...p.points, btc_price: [1, 'x', 3] } }),
			/btc_price\[1\]/
		],
		[
			'an unknown band',
			(p) => ({ ...p, current: { ...p.current, band: 'euphoria' } }),
			/current\.band/
		],
		['a missing current reading', (p) => ({ ...p, current: undefined }), /current/],
		['a non-boolean stale flag', (p) => ({ ...p, stale: 'yes' }), /stale/],
		['no bands', (p) => ({ ...p, bands: [] }), /bands/],
		['a missing source', (p) => ({ ...p, source: undefined }), /source/]
	];
	it.each(bad)('rejects %s', (_name, mutate, pattern) => {
		expect(() => parseFearGreed(mutate(fearGreed()))).toThrow(ApiError);
		expect(() => parseFearGreed(mutate(fearGreed()))).toThrow(pattern);
	});
});

const grid = (rows: number, cols: number, value: number | null = 1) =>
	Array.from({ length: rows }, () => Array.from({ length: cols }, () => value));

const seasonal = (n: number) => ({
	labels: Array.from({ length: n }, (_, i) => String(i)),
	mean_return_pct: Array.from({ length: n }, () => 0.01),
	hit_rate_pct: Array.from({ length: n }, () => 50),
	count: Array.from({ length: n }, () => 10)
});

const charts = (overrides: Record<string, unknown> = {}) => ({
	id: 'abc',
	symbol: 'BINANCE_BTCUSDT',
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
		outliers: { below: 0, above: 1 },
		stats: {
			count: 27,
			mean_pct: 0.01,
			std_pct: 0.4,
			skew: null,
			excess_kurtosis: 1.2,
			min_pct: -1.1,
			max_pct: 1.3,
			positive_pct: 52,
			var_95_pct: -0.7,
			cvar_95_pct: -0.9
		}
	},
	drawdown: {
		time: [1, 2, 3],
		drawdown_pct: [0, -1, -0.5],
		max_drawdown_pct: -1,
		peak_time: 1,
		trough_time: 2,
		recovered_time: null,
		current_drawdown_pct: -0.5,
		longest_underwater_bars: 2
	},
	rolling_volatility: { window: 30, time: [1, 2, 3], value_pct: [null, 0.2, 0.3] },
	activity: {
		hours: Array.from({ length: 24 }, (_, i) => i),
		weekdays: [0, 1, 2, 3, 4, 5, 6],
		metrics: { volume: grid(7, 24), range_pct: grid(7, 24), return_pct: grid(7, 24, null) },
		counts: grid(7, 24)
	},
	seasonality: { by_weekday: seasonal(7), by_hour: seasonal(24) },
	unavailable: {},
	...overrides
});

describe('parseCharts', () => {
	it('accepts a full payload', () => {
		const parsed = parseCharts(charts());
		expect(parsed.volume_profile.volume).toHaveLength(3);
		expect(parsed.return_distribution?.stats.skew).toBeNull();
		expect(parsed.rolling_volatility?.value_pct[0]).toBeNull();
		expect(parsed.activity?.metrics.return_pct[0][0]).toBeNull();
		expect(parsed.seasonality.by_hour?.labels).toHaveLength(24);
		expect(parsed.unavailable).toEqual({});
	});

	it('accepts nulls for every section the backend could not compute, with their reasons', () => {
		const parsed = parseCharts(
			charts({
				return_distribution: null,
				drawdown: null,
				rolling_volatility: null,
				activity: null,
				seasonality: { by_weekday: null, by_hour: null },
				unavailable: { activity: 'needs intraday bars', drawdown: 'needs at least two bars' }
			})
		);
		expect(parsed.return_distribution).toBeNull();
		expect(parsed.drawdown).toBeNull();
		expect(parsed.activity).toBeNull();
		expect(parsed.seasonality).toEqual({ by_weekday: null, by_hour: null });
		expect(parsed.unavailable.activity).toBe('needs intraday bars');
	});

	const bad: [string, Record<string, unknown>, RegExp][] = [
		[
			'profile edges that do not match the volumes',
			{ volume_profile: { ...charts().volume_profile, edges: [100, 110] } },
			/volume_profile\.edges/
		],
		[
			'a normal curve of the wrong length',
			{ return_distribution: { ...charts().return_distribution, normal: [1, 2] } },
			/normal/
		],
		[
			'a drawdown series shorter than its time axis',
			{ drawdown: { ...charts().drawdown, drawdown_pct: [0] } },
			/drawdown_pct/
		],
		[
			'a volatility series shorter than its time axis',
			{ rolling_volatility: { window: 30, time: [1, 2, 3], value_pct: [0.1] } },
			/value_pct/
		],
		[
			'a heatmap grid with the wrong number of rows',
			{ activity: { ...charts().activity, counts: grid(6, 24) } },
			/counts/
		],
		[
			'a heatmap row with the wrong number of columns',
			{ activity: { ...charts().activity, counts: grid(7, 23) } },
			/counts/
		],
		[
			'weekday seasonality with the wrong label count',
			{ seasonality: { by_weekday: seasonal(6), by_hour: null } },
			/labels/
		],
		['a non-text unavailable reason', { unavailable: { activity: 5 } }, /unavailable\.activity/],
		['a missing volume profile', { volume_profile: undefined }, /volume_profile/],
		['a non-boolean intraday flag', { intraday: 'yes' }, /intraday/]
	];
	it.each(bad)('rejects %s', (_name, overrides, pattern) => {
		expect(() => parseCharts(charts(overrides))).toThrow(ApiError);
		expect(() => parseCharts(charts(overrides))).toThrow(pattern);
	});
});

describe('parseCorrelation', () => {
	const good = {
		labels: ['A', 'B'],
		matrix: [
			[1, 0.5],
			[0.5, 1]
		],
		observations: 99,
		start: 1,
		end: 2
	};
	it('accepts a square matrix, keeping null cells', () => {
		expect(parseCorrelation(good).matrix[0][1]).toBe(0.5);
		expect(
			parseCorrelation({
				...good,
				matrix: [
					[1, null],
					[null, 1]
				]
			}).matrix[0][1]
		).toBeNull();
	});
	it.each([
		['fewer than two labels', { ...good, labels: ['A'], matrix: [[1]] }, /labels/],
		['a non-square matrix', { ...good, matrix: [[1, 0.5]] }, /matrix/],
		['a short row', { ...good, matrix: [[1], [0.5, 1]] }, /matrix\[0\]/],
		[
			'a value above 1',
			{
				...good,
				matrix: [
					[1, 1.5],
					[1.5, 1]
				]
			},
			/between -1 and 1/
		],
		[
			'a value below -1',
			{
				...good,
				matrix: [
					[1, -1.2],
					[-1.2, 1]
				]
			},
			/between -1 and 1/
		]
	])('rejects %s', (_name, body, pattern) => {
		expect(() => parseCorrelation(body)).toThrow(pattern);
	});
	it('tolerates rounding just outside the range', () => {
		expect(() =>
			parseCorrelation({
				...good,
				matrix: [
					[1, 1.0000000001],
					[1, 1]
				]
			})
		).not.toThrow();
	});
});

describe('api client: sentiment and charts', () => {
	it('asks for the Fear & Greed index once, with no retries, and a days window', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () =>
			json({ detail: 'CoinMarketCap did not respond in time.' }, 502)
		);
		const error = await createApiClient({ fetch, retryDelayMs: 1 })
			.getFearGreed({ days: 30.9 })
			.catch((e) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect(error.message).toBe('CoinMarketCap did not respond in time.');
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch.mock.calls[0][0]).toBe('/api/sentiment/fear-greed?days=30');
	});

	it('parses a good Fear & Greed response and omits days when not asked', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json(fearGreed()));
		const result = await createApiClient({ fetch }).getFearGreed();
		expect(result.current.label).toBe('Greed');
		expect(fetch.mock.calls[0][0]).toBe('/api/sentiment/fear-greed');
	});

	it('rejects a Fear & Greed body that breaks the contract instead of rendering it', async () => {
		const broken = fearGreed({
			points: { time: [1, 2], score: [50], btc_price: [], btc_volume: [] }
		});
		const error = await createApiClient({ fetch: async () => json(broken) })
			.getFearGreed()
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'contract' });
	});

	it('builds the charts query, url-encoding the id and truncating numbers', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json(charts()));
		await createApiClient({ fetch }).getCharts('a/b c', {
			bins: 60.7,
			valueArea: 0.7,
			window: 30,
			returnBins: 41
		});
		expect(fetch.mock.calls[0][0]).toBe(
			'/api/datasets/a%2Fb%20c/charts?bins=60&value_area=0.7&window=30&return_bins=41'
		);
		await createApiClient({ fetch }).getCharts('x');
		expect(fetch.mock.calls[1][0]).toBe('/api/datasets/x/charts');
	});

	it('repeats the ids parameter for the correlation endpoint', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () =>
			json({
				labels: ['A', 'B'],
				matrix: [
					[1, 0.2],
					[0.2, 1]
				],
				observations: 10,
				start: 1,
				end: 2
			})
		);
		const result = await createApiClient({ fetch }).getCorrelation(['a b', 'c']);
		expect(result.observations).toBe(10);
		expect(fetch.mock.calls[0][0]).toBe('/api/charts/correlation?ids=a+b&ids=c');
	});
});
