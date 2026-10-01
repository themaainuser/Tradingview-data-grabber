/**
 * Test-only builders for provider payloads, in the exact JSON shape the backend returns.
 * Never imported by app code.
 */
import type {
	Catalog,
	CatalogCategory,
	CatalogEndpoint,
	CatalogParam,
	ProviderSummary,
	ProviderView,
	QueryResponse,
	SeriesView
} from '$lib/api/providers';

export const param = (over: Partial<CatalogParam> = {}): CatalogParam => ({
	name: 'symbol',
	required: true,
	type: 'text',
	description: 'The symbol of your choice.',
	enum: [],
	enum_labels: {},
	suggestions: [],
	default: null,
	example: 'IBM',
	multiple: false,
	premium_note: null,
	managed: false,
	...over
});

export const endpoint = (id: string, over: Partial<CatalogEndpoint> = {}): CatalogEndpoint => ({
	id,
	title: id,
	category: 'stocks',
	description: `${id} returns data. It is documented here.`,
	summary: `${id} returns data.`,
	premium: false,
	trending: false,
	utility: false,
	premium_notes: [],
	doc_url: `https://provider.test/docs#${id.toLowerCase()}`,
	params: [param()],
	examples: [{ caption: 'IBM', params: { symbol: 'IBM' } }],
	...over
});

export const provider = (over: Partial<ProviderSummary> = {}): ProviderSummary => ({
	id: 'alphavantage',
	name: 'Alpha Vantage',
	description: 'Market data.',
	website: 'https://www.alphavantage.co/',
	docs_url: 'https://www.alphavantage.co/documentation/',
	key_env: 'ALPHAVANTAGE_API_KEY',
	key_url: 'https://www.alphavantage.co/support/#api-key',
	configured: true,
	endpoint_count: 5,
	premium_count: 2,
	limits_note: 'Free keys allow 25 requests per day.',
	requests_this_session: 0,
	...over
});

/** Five endpoints: two premium, one with a premium-gated parameter, one of every parameter type. */
export const ENDPOINTS: CatalogEndpoint[] = [
	endpoint('TIME_SERIES_DAILY', {
		title: 'Daily prices',
		params: [
			param(),
			param({
				name: 'outputsize',
				required: false,
				type: 'enum',
				enum: ['compact', 'full'],
				example: null,
				default: 'compact',
				premium_note: 'The "full" outputsize is available to premium keys.'
			}),
			param({
				name: 'datatype',
				required: false,
				type: 'enum',
				enum: ['json', 'csv'],
				example: null,
				managed: true
			})
		],
		examples: [
			{ caption: 'IBM', params: { symbol: 'IBM' } },
			// Real documentation captions are whole sentences.
			{
				caption:
					'Set require_greeks=true to enable greeks & implied volatility (IV) fields in the API response',
				params: { symbol: 'MSFT' }
			}
		]
	}),
	endpoint('TIME_SERIES_INTRADAY', {
		title: 'Intraday prices',
		premium: true,
		trending: true,
		premium_notes: ['This is a premium endpoint.'],
		params: [
			param(),
			param({ name: 'interval', type: 'enum', enum: ['1min', '5min', '60min'], example: '5min' }),
			param({
				name: 'adjusted',
				required: false,
				type: 'boolean',
				enum: ['true', 'false'],
				example: null,
				default: 'true'
			}),
			param({ name: 'month', required: false, type: 'month', example: null }),
			param({
				name: 'entitlement',
				required: false,
				type: 'text',
				suggestions: ['realtime', 'delayed'],
				example: null
			})
		],
		examples: [
			{ caption: 'Five minute bars', params: { symbol: 'IBM', interval: '5min' } },
			{ caption: 'A past month', params: { symbol: 'IBM', interval: '5min', month: '2009-01' } }
		]
	}),
	endpoint('SMA', {
		title: 'Simple moving average',
		category: 'indicators',
		params: [
			param(),
			param({ name: 'time_period', type: 'number', example: '10' }),
			param({ name: 'date', required: false, type: 'date', example: null })
		],
		examples: [{ caption: 'SMA', params: { symbol: 'IBM', time_period: '10' } }]
	}),
	endpoint('ANALYTICS_FIXED_WINDOW', {
		title: 'Analytics (fixed window)',
		category: 'indicators',
		params: [
			param({ name: 'SYMBOLS', example: 'AAPL,IBM' }),
			param({ name: 'RANGE', type: 'date', multiple: true, example: '2023-07-01' })
		],
		examples: [
			{
				caption: 'Two ranges',
				params: { SYMBOLS: 'AAPL,IBM', RANGE: ['2023-07-01', '2023-08-31'] }
			}
		]
	}),
	endpoint('REALTIME_OPTIONS', {
		title: 'Realtime options',
		category: 'options',
		premium: true,
		premium_notes: ['Premium only.']
	})
];

export const CATEGORIES: CatalogCategory[] = [
	{ id: 'stocks', title: 'Stocks', summary: '', count: 2, premium_count: 1 },
	{ id: 'indicators', title: 'Technical indicators', summary: '', count: 2, premium_count: 0 },
	{ id: 'options', title: 'Options', summary: '', count: 1, premium_count: 1 }
];

export const catalog = (
	p: ProviderSummary = provider(),
	endpoints: CatalogEndpoint[] = ENDPOINTS
): Catalog => ({
	provider: p,
	categories: CATEGORIES,
	endpoints
});

const DAY = 86_400;
const START = 1_788_000_000;

/** An OHLCV series of `n` days. */
export function seriesView(n = 40, over: Partial<SeriesView> = {}): SeriesView {
	const time = Array.from({ length: n }, (_, i) => START + i * DAY);
	const close = time.map((_, i) => 100 + i + (i % 3));
	return {
		kind: 'series',
		id: 'series',
		title: 'Price history',
		subtitle: 'IBM · Daily Prices',
		time,
		intraday: false,
		series: [
			{ key: 'open', label: 'open', values: close.map((c) => c - 1), role: 'open', unit: null },
			{ key: 'high', label: 'high', values: close.map((c) => c + 2), role: 'high', unit: null },
			{ key: 'low', label: 'low', values: close.map((c) => c - 2), role: 'low', unit: null },
			{ key: 'close', label: 'close', values: close, role: 'close', unit: null },
			{
				key: 'volume',
				label: 'volume',
				values: close.map((c) => c * 1000),
				role: 'volume',
				unit: null
			}
		],
		time_note: null,
		truncated: false,
		total_points: n,
		...over
	};
}

export const lineView = (): ProviderView => ({
	...seriesView(30, { id: 'line', title: 'Simple Moving Average (SMA)' }),
	series: [
		{
			key: 'sma',
			label: 'SMA',
			values: Array.from({ length: 30 }, (_, i) => 200 + i),
			role: 'value',
			unit: 'USD'
		}
	]
});

export const tableView = (rows = 12): ProviderView => ({
	kind: 'table',
	id: 'table',
	title: 'Rows',
	subtitle: 'Newest first',
	columns: [
		{ key: 'date', label: 'Date', type: 'date' },
		{ key: 'name', label: 'Name', type: 'text' },
		{ key: 'price', label: 'Price', type: 'number' },
		{ key: 'change', label: 'Change', type: 'percent' }
	],
	rows: Array.from({ length: rows }, (_, i) => [
		`2026-09-${String(28 - (i % 28)).padStart(2, '0')}`,
		`Row ${i}`,
		100 + i * 1.5,
		i % 2 ? -1.25 : 2.5
	]),
	total_rows: rows,
	truncated: false
});

export const factsView = (): ProviderView => ({
	kind: 'facts',
	id: 'summary',
	title: 'Summary',
	subtitle: null,
	groups: [
		{
			title: 'Latest',
			items: [
				{
					key: 'latest',
					label: 'Latest close',
					value: 221.5,
					format: 'number',
					tone: null,
					hint: null
				},
				{
					key: 'change',
					label: 'Change vs previous',
					value: -1.25,
					format: 'number',
					tone: 'negative',
					hint: null
				},
				{
					key: 'period',
					label: 'Change over the period',
					value: 3.4,
					format: 'percent',
					tone: 'positive',
					hint: 'Over 40 days'
				},
				{
					key: 'site',
					label: 'Website',
					value: 'https://www.ibm.com',
					format: 'url',
					tone: null,
					hint: null
				},
				{ key: 'missing', label: 'Unreported', value: null, format: 'text', tone: null, hint: null }
			]
		}
	]
});

export const barsView = (): ProviderView => ({
	kind: 'bars',
	id: 'bars',
	title: 'Biggest moves',
	subtitle: null,
	labels: ['UP', 'DN'],
	values: [12.5, -8.25],
	format: 'percent',
	sign_colors: true,
	value_label: 'Change'
});

export const feedView = (): ProviderView => ({
	kind: 'feed',
	id: 'feed',
	title: 'Articles',
	subtitle: 'Newest first',
	items: [
		{
			title: 'IBM beats expectations',
			url: 'https://news.test/a',
			source: 'Wire',
			published: START,
			summary: 'A summary.',
			sentiment: { score: 0.4, label: 'Bullish' },
			tags: ['Earnings'],
			tickers: [{ symbol: 'IBM', relevance: 1, score: 0.4, label: 'Bullish' }]
		},
		{
			title: 'Unlinked story',
			url: null,
			source: null,
			published: null,
			summary: null,
			sentiment: null,
			tags: [],
			tickers: []
		}
	],
	total_items: 2,
	truncated: false
});

export const heatmapView = (): ProviderView => ({
	kind: 'heatmap',
	id: 'heat',
	title: 'Correlation',
	subtitle: null,
	rows: ['AAPL', 'IBM'],
	cols: ['AAPL', 'IBM'],
	values: [
		[1, 0.25],
		[0.25, 1]
	],
	scale: 'diverging',
	domain: [-1, 1]
});

export const textView = (): ProviderView => ({
	kind: 'text',
	id: 'text',
	title: 'Transcript',
	subtitle: 'IBM 2024Q1',
	blocks: [
		{
			heading: 'Olympia',
			subheading: 'Investor Relations',
			body: 'Welcome to the call. '.repeat(40),
			badge: 'Sentiment +0.60'
		}
	],
	total_blocks: 1,
	truncated: false
});

export const ALL_VIEWS = (): ProviderView[] => [
	factsView(),
	seriesView(),
	lineView(),
	barsView(),
	feedView(),
	heatmapView(),
	tableView(),
	textView()
];

export function response(over: Partial<QueryResponse> = {}): QueryResponse {
	return {
		provider: 'alphavantage',
		endpoint: 'TIME_SERIES_DAILY',
		title: 'Daily prices',
		status: 'ok',
		message: null,
		cached: false,
		fetched_at: 1_790_000_000,
		elapsed_ms: 187,
		bytes: 24_300,
		params: { function: 'TIME_SERIES_DAILY', symbol: 'IBM' },
		views: [factsView(), seriesView(), tableView()],
		raw: { 'Meta Data': { '2. Symbol': 'IBM' } },
		raw_omitted: null,
		notes: [],
		...over
	};
}

/** A non-ok response: no views, a message. */
export const failure = (status: QueryResponse['status'], message: string): QueryResponse =>
	response({ status, message, views: [], raw: null, fetched_at: null });
