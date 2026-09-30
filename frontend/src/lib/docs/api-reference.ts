/**
 * Hand-written reference for the FastAPI backend (`tradingview_data/api.py`).
 *
 * The backend also publishes a generated schema at `/api/openapi.json` with Swagger at `/api/docs`;
 * this is the readable version. `docs.spec.ts` pins the set of paths so adding an endpoint on
 * one side without the other shows up in tests.
 */

export interface EndpointParam {
	name: string;
	in: 'path' | 'query' | 'body';
	type: string;
	required: boolean;
	description: string;
}

export interface EndpointError {
	status: number;
	when: string;
}

export interface Endpoint {
	id: string;
	method: 'GET' | 'POST';
	path: string;
	summary: string;
	params: EndpointParam[];
	returns: string;
	errors: EndpointError[];
	/** Where the dashboard calls it, or null when it is available but not used yet. */
	usedBy: string | null;
}

export const API_ENDPOINTS: readonly Endpoint[] = [
	{
		id: 'health',
		method: 'GET',
		path: '/api/health',
		summary: 'Liveness check and the data directory being served.',
		params: [],
		returns: '{ status: "ok", data_dir: string, dataset_count: number }',
		errors: [],
		usedBy: null
	},
	{
		id: 'datasets',
		method: 'GET',
		path: '/api/datasets',
		summary:
			'Every capture found in the data directory, sorted by symbol then timeframe. Unreadable files are listed with valid: false and an error message instead of failing the listing.',
		params: [],
		returns:
			'{ datasets: { id, symbol, timeframe, path, rows, size_bytes, modified, start, end, valid, error }[] }',
		errors: [],
		usedBy: 'Datasets page, dataset pickers'
	},
	{
		id: 'bars',
		method: 'GET',
		path: '/api/datasets/{id}/bars',
		summary:
			'Columnar OHLCV for one dataset. Times are UTC epoch seconds. quality and the dropped/duplicate counters describe the whole file, not the returned window.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			},
			{
				name: 'limit',
				in: 'query',
				type: 'integer 1 to 5,000,000',
				required: false,
				description: 'Keep only the most recent N bars of the requested window.'
			},
			{
				name: 'start',
				in: 'query',
				type: 'number',
				required: false,
				description: 'First bar to include, epoch seconds (inclusive).'
			},
			{
				name: 'end',
				in: 'query',
				type: 'number',
				required: false,
				description: 'Last bar to include, epoch seconds (inclusive).'
			}
		],
		returns:
			'{ id, symbol, timeframe, rows, total_rows, dropped_rows, duplicate_rows_collapsed, columns: { time, open, high, low, close, volume }, quality }',
		errors: [
			{ status: 404, when: 'The id does not match a scanned file.' },
			{ status: 422, when: 'The file fails validation, or start is greater than end.' }
		],
		usedBy: 'Explorer'
	},
	{
		id: 'report',
		method: 'GET',
		path: '/api/datasets/{id}/report',
		summary:
			'The technical summary that the tvdata analyze command prints: data quality, latest bar, indicators and signals.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			}
		],
		returns: 'The market report object (quality, latest, performance, indicators, signals).',
		errors: [
			{ status: 404, when: 'The id does not match a scanned file.' },
			{ status: 422, when: 'The file fails validation.' }
		],
		usedBy: null
	},
	{
		id: 'charts',
		method: 'GET',
		path: '/api/datasets/{id}/charts',
		summary:
			'Chart data for one dataset, computed by the same code that draws the PNG charts: volume profile, return distribution, drawdown, rolling volatility, UTC hour-by-weekday activity grids and seasonality. A section that needs more bars, or intraday bars, is null and explained under unavailable.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			},
			{
				name: 'bins',
				in: 'query',
				type: 'integer 10 to 200',
				required: false,
				description: 'Price bins of the volume profile. Default 60.'
			},
			{
				name: 'value_area',
				in: 'query',
				type: 'number 0.5 to 0.95',
				required: false,
				description: 'Share of volume inside the value area. Default 0.7.'
			},
			{
				name: 'window',
				in: 'query',
				type: 'integer 5 to 500',
				required: false,
				description: 'Rolling volatility window in bars. Default 30.'
			},
			{
				name: 'return_bins',
				in: 'query',
				type: 'integer 10 to 101',
				required: false,
				description: 'Bins of the return histogram. Default 41.'
			}
		],
		returns:
			'{ id, symbol, timeframe, bars, interval_seconds, intraday, volume_profile, return_distribution, drawdown, rolling_volatility, activity, seasonality, unavailable }',
		errors: [
			{ status: 404, when: 'The id does not match a scanned file.' },
			{ status: 422, when: 'The file fails validation, or a parameter is outside its range.' }
		],
		usedBy: 'Charts'
	},
	{
		id: 'correlation',
		method: 'GET',
		path: '/api/charts/correlation',
		summary:
			'Correlation of bar-to-bar returns across datasets, over the timestamps they share. Repeat the ids parameter once per dataset.',
		params: [
			{
				name: 'ids',
				in: 'query',
				type: 'string[] (2 to 20, unique)',
				required: true,
				description: 'Dataset ids from /api/datasets.'
			}
		],
		returns: '{ labels, matrix, observations, start, end }',
		errors: [
			{
				status: 422,
				when: 'Fewer than two or more than twenty ids, a duplicate or unknown id, a file that fails validation, or fewer than 3 overlapping returns.'
			}
		],
		usedBy: 'Charts (Correlation)'
	},
	{
		id: 'fear-greed',
		method: 'GET',
		path: '/api/sentiment/fear-greed',
		summary:
			"CoinMarketCap's Crypto Fear and Greed Index, read by the backend from the public endpoint CoinMarketCap's own chart page uses (no API key). That endpoint is not a published API. Results are cached for ten minutes; if a refresh fails the last good readings are returned with stale: true. Nothing is ever substituted for a missing reading.",
		params: [
			{
				name: 'days',
				in: 'query',
				type: 'integer 1 to 3650',
				required: false,
				description: 'Return only the last N days of history.'
			}
		],
		returns:
			'{ source, fetched_at, stale, stale_reason, bands, current, snapshots, points: { time, score, btc_price, btc_volume }, total_points }',
		errors: [
			{ status: 502, when: 'CoinMarketCap could not be read and no earlier reading is cached.' }
		],
		usedBy: 'Sentiment'
	},
	{
		id: 'research',
		method: 'POST',
		path: '/api/research/run',
		summary:
			'Backtests the built-in strategy grid (SMA crossovers and RSI mean reversion) on each dataset, with fixed rules and forward folds. No language model is called.',
		params: [
			{
				name: 'dataset_ids',
				in: 'body',
				type: 'string[] (1 to 20, unique)',
				required: true,
				description: 'Ids from /api/datasets. assets[i] in the response matches dataset_ids[i].'
			},
			{
				name: 'fee_bps',
				in: 'body',
				type: 'number 0 to 10,000',
				required: false,
				description: 'Cost per position change in basis points. Default 5.'
			},
			{
				name: 'periods_per_year',
				in: 'body',
				type: 'number > 0',
				required: false,
				description: 'Annualisation factor for Sharpe, Sortino and CAGR. Default 252.'
			}
		],
		returns: '{ schema_version: 1, metadata, assets, results, model_notes, disclosures }',
		errors: [
			{
				status: 422,
				when: 'Unknown dataset id, a file that fails validation, or an invalid parameter.'
			}
		],
		usedBy: 'Research'
	}
];
