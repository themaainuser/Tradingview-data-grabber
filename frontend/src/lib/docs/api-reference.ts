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
