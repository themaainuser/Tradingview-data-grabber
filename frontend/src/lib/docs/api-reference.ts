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
		id: 'verdict-run',
		method: 'POST',
		path: '/api/verdict/run',
		summary:
			'Runs the honest verdict engine on the research window of one dataset: next-open fills, fees, spread and slippage on both sides, a trade-count gate, then (only for rules that pass it) a block bootstrap, deflated Sharpe ratio, probability of backtest overfitting and cost stress tests. Appends the run to the trial ledger and answers with exactly one of INSUFFICIENT_DATA, INDISTINGUISHABLE_FROM_LUCK or CANDIDATE.',
		params: [
			{
				name: 'dataset_id',
				in: 'body',
				type: 'string',
				required: true,
				description: 'Id from /api/datasets.'
			},
			{
				name: 'min_trades',
				in: 'body',
				type: 'integer 1 to 1000',
				required: false,
				description: 'Entries a rule needs before it gets any statistic. Default 30.'
			},
			{
				name: 'costs',
				in: 'body',
				type: '{ fee_bps_per_side, spread_bps, slippage_k }',
				required: false,
				description:
					'Per-side costs. Defaults 10 bps, 1 bps and 0.1 x ATR(14); verify them against your venue.'
			},
			{
				name: 'periods_per_year',
				in: 'body',
				type: 'number > 0 or null',
				required: false,
				description:
					'Annualisation factor. null infers it from the bar spacing, assuming continuous trading.'
			}
		],
		returns:
			'{ run_id, verdict: { label, headline, reasons }, settings, data, ledger, rules, statistics, uncertainty, integrity, notes }',
		errors: [
			{ status: 404, when: 'The dataset id is unknown.' },
			{
				status: 409,
				when: 'The ledger chain does not verify, or the bars before the seal changed since sealing.'
			},
			{
				status: 422,
				when: 'The file fails validation, has too few bars to seal, or a setting is out of range.'
			}
		],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-state',
		method: 'GET',
		path: '/api/verdict/{id}',
		summary:
			'The current state of one dataset: whether its holdout is sealed, the ledger counts, the latest verdict, any frozen rules, the stored holdout result and the form defaults. Read-only: it never writes to the ledger.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			}
		],
		returns: '{ dataset, sealed, holdout, ledger, latest, freeze, holdout_read, defaults }',
		errors: [{ status: 404, when: 'The id does not match a scanned file.' }],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-seal',
		method: 'POST',
		path: '/api/verdict/{id}/seal',
		summary:
			'Seals the most recent share of a dataset\u2019s bars as a holdout before any analysis. It is excluded from every research query from then on. Needs at least 100 bars.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			},
			{
				name: 'holdout_fraction',
				in: 'body',
				type: 'number 0.10 to 0.30',
				required: false,
				description: 'Share of the most recent bars to seal. Default 0.20.'
			}
		],
		returns: '{ holdout: { fraction, start, end, bars, sealed_at, status, read_at } }',
		errors: [
			{ status: 409, when: 'The dataset is already sealed.' },
			{ status: 422, when: 'Too few bars, or the share is out of range.' }
		],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-ledger',
		method: 'GET',
		path: '/api/verdict/{id}/ledger',
		summary:
			'The trial ledger: N for the dataset and in total, every distinct rule tried, and the most recent entries, with whether the hash chain still verifies.',
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
				type: 'integer 1 to 500',
				required: false,
				description: 'How many recent entries to return. Default 100.'
			}
		],
		returns: '{ intact, total_entries, trials: { dataset, total, keys }, entries }',
		errors: [{ status: 404, when: 'The id does not match a scanned file.' }],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-freeze',
		method: 'POST',
		path: '/api/verdict/{id}/freeze',
		summary:
			'Freezes one or two candidate rules, with their parameters and cost settings, under a hash in the ledger. Only rules that are candidates in the latest run can be frozen, and there is one freeze per dataset.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			},
			{
				name: 'run_id',
				in: 'body',
				type: 'string',
				required: true,
				description: 'The latest completed run, whose label must be CANDIDATE.'
			},
			{
				name: 'rule_ids',
				in: 'body',
				type: 'string[] (1 to 2, unique)',
				required: true,
				description: 'Candidate rules from that run.'
			}
		],
		returns: '{ id, run_id, rule_ids, rules, frozen_at, forward_start, hash }',
		errors: [
			{ status: 409, when: 'Rules are already frozen, or the ledger chain does not verify.' },
			{
				status: 422,
				when: 'The run is not the latest, is not a CANDIDATE, or a rule is not a candidate in it.'
			}
		],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-holdout-read',
		method: 'POST',
		path: '/api/verdict/{id}/holdout/read',
		summary:
			'Evaluates the frozen rules on the sealed holdout. It can be done once per seal: a second read, with any rule set, is refused. The result is stored, so the page can show it again without reading twice. With a few hundred bars it is a sanity check, not a verdict.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			},
			{
				name: 'freeze_id',
				in: 'body',
				type: 'string',
				required: true,
				description: 'The freeze to read the holdout for.'
			}
		],
		returns: '{ freeze_id, read_at, start, end, bars, rules, caveat, sharpe_se_annualised_iid }',
		errors: [
			{ status: 409, when: 'Nothing is frozen, or the holdout was already read.' },
			{ status: 422, when: 'The freeze id does not match.' }
		],
		usedBy: 'Verdict'
	},
	{
		id: 'verdict-forward',
		method: 'GET',
		path: '/api/verdict/{id}/forward',
		summary:
			'The frozen rules evaluated only on bars captured after the freeze: the real out-of-sample record. Not stored; it grows as the capture runs, and is marked waiting until the first new bar arrives.',
		params: [
			{
				name: 'id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'Opaque id from /api/datasets.'
			}
		],
		returns: '{ freeze, start, end, bars, waiting, rules, caveat, sharpe_se_annualised_iid }',
		errors: [{ status: 409, when: 'Nothing is frozen.' }],
		usedBy: 'Verdict'
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
		id: 'providers',
		method: 'GET',
		path: '/api/providers',
		summary:
			"The external data providers the backend offers, in the order of the Providers page's dropdown. Reports whether each provider's API key is set in the backend's environment, and never the key itself.",
		params: [],
		returns:
			'{ providers: [{ id, name, description, website, docs_url, key_env, key_url, configured, endpoint_count, premium_count, limits_note, plans: [{ name, summary }], requests_this_session }] }',
		errors: [],
		usedBy: 'Providers'
	},
	{
		id: 'provider-catalog',
		method: 'GET',
		path: '/api/providers/{provider_id}/catalog',
		summary:
			"A provider's endpoints with their parameters, which endpoints and options are premium (for a provider with subscription tiers, also the plan that first includes each endpoint, the premium choices of a parameter, and how many requests one fetch costs), links to its documentation and the examples it documents. Needs no API key and contacts no one: the catalog is built from the provider's documentation when the catalog file is updated.",
		params: [
			{
				name: 'provider_id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'A provider id from /api/providers.'
			}
		],
		returns: '{ provider, categories, endpoints }',
		errors: [{ status: 404, when: 'No provider has this id.' }],
		usedBy: 'Providers'
	},
	{
		id: 'provider-query',
		method: 'POST',
		path: '/api/providers/{provider_id}/query',
		summary:
			"Fetches one endpoint from the provider and returns it as views to draw (series, table, facts, bars, feed, heatmap, text). The provider's API key is added by the backend and never appears in a response. Identical successful requests are cached for five minutes. Premium refusals, rate limits, a missing or rejected key and empty answers come back as HTTP 200 with a status and a message and no views; a response the provider marks as sample data is never turned into views.",
		params: [
			{
				name: 'provider_id',
				in: 'path',
				type: 'string',
				required: true,
				description: 'A provider id from /api/providers.'
			},
			{
				name: 'endpoint',
				in: 'body',
				type: 'string',
				required: true,
				description: "An endpoint id from the provider's catalog."
			},
			{
				name: 'params',
				in: 'body',
				type: 'object',
				required: false,
				description:
					"The endpoint's parameters as strings (a repeated parameter is a list). Checked against the catalog before anything is sent; the key and the response format are set by the server."
			},
			{
				name: 'refresh',
				in: 'body',
				type: 'boolean',
				required: false,
				description:
					'Skip the cache and ask the provider again. This uses one request from its quota.'
			}
		],
		returns:
			'{ provider, endpoint, title, status, message, cached, fetched_at, elapsed_ms, bytes, params, views, raw, raw_omitted, notes }',
		errors: [
			{ status: 404, when: 'No provider or no endpoint has this id.' },
			{ status: 422, when: 'A parameter is missing, unknown or invalid.' }
		],
		usedBy: 'Providers'
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
