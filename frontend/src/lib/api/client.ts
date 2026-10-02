import { ApiError, toApiError } from './errors';
import type {
	ChartsResponse,
	CorrelationResponse,
	DatasetSummary,
	FearGreedResponse,
	ForwardResult,
	HoldoutInfo,
	HoldoutResult,
	LedgerView,
	ResearchReport,
	ResearchRequest,
	VerdictFreeze,
	VerdictReport,
	VerdictRequest,
	VerdictState
} from './contracts';
import {
	parseBars,
	parseCharts,
	parseCorrelation,
	parseDatasetList,
	parseFearGreed,
	parseResearch,
	type Bars
} from './validate';
import {
	parseForward,
	parseFreeze,
	parseHoldoutInfo,
	parseHoldoutResult,
	parseLedger,
	parseVerdictReport,
	parseVerdictState
} from './verdict';
import {
	parseEnvelope,
	parseEnvironments,
	type Envelope,
	type TradingEnvironments
} from './trading';
import {
	parseCatalog,
	parseProviders,
	parseQueryResponse,
	type Catalog,
	type ProviderSummary,
	type QueryResponse,
	type ParamValues
} from './providers';

export interface ApiClientOptions {
	baseUrl?: string;
	/** Injectable for tests; defaults to the global fetch. */
	fetch?: typeof fetch;
	/** Per-attempt timeout. Research runs are long, so callers can override per request. */
	timeoutMs?: number;
	/** Extra attempts for idempotent GETs after a network fault or 5xx. */
	retries?: number;
	retryDelayMs?: number;
}

/** One call to the trading API. `path` is what follows `/api/trading/{env}`; its parts must already be encoded. */
export interface TradingCall {
	method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
	path: string;
	query?: Record<string, string | undefined>;
	body?: unknown;
}

/** Marks a request as coming from the dashboard; the backend refuses a trading change without it. */
export const TRADING_HEADER = 'X-Tvdata-Trading';

export interface RequestOptions {
	signal?: AbortSignal;
	timeoutMs?: number;
	/** Overrides the client's retry count for this GET (0 = try once). */
	retries?: number;
}

/** FastAPI sends `{detail: string}` or, for validation, `{detail: [{loc, msg}]}`. */
export function extractDetail(body: unknown): string | null {
	if (typeof body !== 'object' || body === null) return null;
	const detail = (body as { detail?: unknown }).detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		const parts = detail.map((item) => {
			if (typeof item !== 'object' || item === null) return String(item);
			const { loc, msg } = item as { loc?: unknown[]; msg?: unknown };
			const where = Array.isArray(loc)
				? loc.filter((l) => l !== 'body' && l !== 'query').join('.')
				: '';
			return where ? `${where}: ${String(msg)}` : String(msg);
		});
		return parts.join('; ') || null;
	}
	return null;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function createApiClient(options: ApiClientOptions = {}) {
	const baseUrl = options.baseUrl ?? '';
	const fetchImpl = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
	const defaultTimeout = options.timeoutMs ?? 30_000;
	const retries = options.retries ?? 2;
	const retryDelay = options.retryDelayMs ?? 400;

	async function attempt(
		path: string,
		init: RequestInit,
		request: RequestOptions
	): Promise<unknown> {
		const timeout = AbortSignal.timeout(request.timeoutMs ?? defaultTimeout);
		const signal = request.signal ? AbortSignal.any([request.signal, timeout]) : timeout;
		let response: Response;
		try {
			response = await fetchImpl(baseUrl + path, { ...init, signal });
		} catch (error) {
			if (request.signal?.aborted) throw new ApiError('aborted', 'Request cancelled', null, error);
			if (timeout.aborted)
				throw new ApiError('timeout', 'The backend took too long to respond', null, error);
			throw new ApiError(
				'network',
				'Cannot reach the backend. Check that `tvdata serve` is running.',
				null,
				error
			);
		}
		let body: unknown = null;
		try {
			const text = await response.text();
			body = text ? JSON.parse(text) : null;
		} catch (error) {
			if (response.ok)
				throw new ApiError('contract', 'The backend returned invalid JSON', response.status, error);
		}
		if (!response.ok) {
			const detail = extractDetail(body);
			throw new ApiError(
				'http',
				detail ??
					`Backend error ${response.status}${response.statusText ? ` ${response.statusText}` : ''}`,
				response.status
			);
		}
		return body;
	}

	/** Mutating calls are never retried: a retry after a timeout could repeat a one-way action. */
	const post = (path: string, body: unknown, opts: RequestOptions) =>
		request(
			path,
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			},
			opts,
			false
		);

	/**
	 * A request that changes something at the broker. Never retried (a retry after a timeout could place an
	 * order twice) and always marked as the dashboard's own, which the backend requires.
	 */
	const change = (
		method: Exclude<TradingCall['method'], 'GET'>,
		path: string,
		body: unknown,
		opts: RequestOptions
	) =>
		request(
			path,
			{
				method,
				headers: {
					[TRADING_HEADER]: '1',
					...(body === undefined ? {} : { 'Content-Type': 'application/json' })
				},
				body: body === undefined ? undefined : JSON.stringify(body)
			},
			opts,
			false
		);

	async function request(path: string, init: RequestInit, opts: RequestOptions, retry: boolean) {
		const attempts = retry ? (opts.retries ?? retries) + 1 : 1;
		let last: ApiError | null = null;
		for (let i = 0; i < attempts; i++) {
			try {
				return await attempt(path, init, opts);
			} catch (error) {
				last = toApiError(error);
				if (!last.retryable || i === attempts - 1 || opts.signal?.aborted) break;
				await sleep(retryDelay * 2 ** i);
			}
		}
		throw last as ApiError;
	}

	return {
		async listDatasets(opts: RequestOptions = {}): Promise<DatasetSummary[]> {
			return parseDatasetList(await request('/api/datasets', {}, opts, true)).datasets;
		},

		async getBars(id: string, opts: RequestOptions & { limit?: number } = {}): Promise<Bars> {
			const query = opts.limit ? `?limit=${Math.trunc(opts.limit)}` : '';
			const json = await request(
				`/api/datasets/${encodeURIComponent(id)}/bars${query}`,
				{},
				opts,
				true
			);
			return parseBars(json);
		},

		/**
		 * The backend fetches CoinMarketCap itself and backs off after a failure, so retrying here only
		 * delays the error message; one attempt is enough.
		 */
		async getFearGreed(opts: RequestOptions & { days?: number } = {}): Promise<FearGreedResponse> {
			const query = opts.days ? `?days=${Math.trunc(opts.days)}` : '';
			return parseFearGreed(
				await request(`/api/sentiment/fear-greed${query}`, {}, { retries: 0, ...opts }, true)
			);
		},

		async getCharts(
			id: string,
			opts: RequestOptions & {
				bins?: number;
				valueArea?: number;
				window?: number;
				returnBins?: number;
			} = {}
		): Promise<ChartsResponse> {
			const params = new URLSearchParams();
			if (opts.bins) params.set('bins', String(Math.trunc(opts.bins)));
			if (opts.valueArea) params.set('value_area', String(opts.valueArea));
			if (opts.window) params.set('window', String(Math.trunc(opts.window)));
			if (opts.returnBins) params.set('return_bins', String(Math.trunc(opts.returnBins)));
			const query = params.size ? `?${params}` : '';
			const json = await request(
				`/api/datasets/${encodeURIComponent(id)}/charts${query}`,
				{},
				opts,
				true
			);
			return parseCharts(json);
		},

		async getCorrelation(
			ids: readonly string[],
			opts: RequestOptions = {}
		): Promise<CorrelationResponse> {
			const params = new URLSearchParams();
			for (const id of ids) params.append('ids', id);
			return parseCorrelation(await request(`/api/charts/correlation?${params}`, {}, opts, true));
		},

		async listProviders(opts: RequestOptions = {}): Promise<ProviderSummary[]> {
			return parseProviders(await request('/api/providers', {}, opts, true));
		},

		async getProviderCatalog(providerId: string, opts: RequestOptions = {}): Promise<Catalog> {
			return parseCatalog(
				await request(`/api/providers/${encodeURIComponent(providerId)}/catalog`, {}, opts, true)
			);
		},

		/**
		 * Fetches one provider endpoint. Never retried: a retry would spend the provider's daily quota
		 * a second time, and provider-side problems come back as a status, not an HTTP error.
		 */
		async queryProvider(
			providerId: string,
			body: { endpoint: string; params: ParamValues; refresh?: boolean },
			opts: RequestOptions = {}
		): Promise<QueryResponse> {
			const json = await post(`/api/providers/${encodeURIComponent(providerId)}/query`, body, {
				timeoutMs: 120_000,
				...opts
			});
			return parseQueryResponse(json);
		},

		async tradingEnvironments(opts: RequestOptions = {}): Promise<TradingEnvironments> {
			return parseEnvironments(await request('/api/trading/environments', {}, opts, true));
		},

		/** Reads are retried like any GET; everything else is sent once. `parse` is `null` when no data is expected. */
		async trading<T>(
			env: string,
			call: TradingCall,
			parse: ((data: unknown) => T) | null,
			opts: RequestOptions = {}
		): Promise<Envelope<T>> {
			const query = new URLSearchParams();
			for (const [name, value] of Object.entries(call.query ?? {}))
				if (value !== undefined && value !== '') query.set(name, value);
			const path = `/api/trading/${encodeURIComponent(env)}${call.path}${query.size > 0 ? `?${query}` : ''}`;
			const json =
				call.method === 'GET'
					? await request(path, {}, opts, true)
					: await change(call.method, path, call.body, { timeoutMs: 60_000, ...opts });
			return parseEnvelope(json, parse);
		},

		async getVerdictState(datasetId: string, opts: RequestOptions = {}): Promise<VerdictState> {
			const json = await request(`/api/verdict/${encodeURIComponent(datasetId)}`, {}, opts, true);
			return parseVerdictState(json);
		},

		/** Appends to the ledger, so it is a POST and never retried automatically. */
		async runVerdict(body: VerdictRequest, opts: RequestOptions = {}): Promise<VerdictReport> {
			return parseVerdictReport(
				await post('/api/verdict/run', body, { timeoutMs: 5 * 60_000, ...opts })
			);
		},

		async sealHoldout(
			datasetId: string,
			fraction: number,
			opts: RequestOptions = {}
		): Promise<HoldoutInfo> {
			const json = await post(
				`/api/verdict/${encodeURIComponent(datasetId)}/seal`,
				{ holdout_fraction: fraction },
				opts
			);
			return parseHoldoutInfo((json as { holdout?: unknown } | null)?.holdout);
		},

		async getVerdictLedger(
			datasetId: string,
			opts: RequestOptions & { limit?: number } = {}
		): Promise<LedgerView> {
			const query = opts.limit ? `?limit=${Math.trunc(opts.limit)}` : '';
			const json = await request(
				`/api/verdict/${encodeURIComponent(datasetId)}/ledger${query}`,
				{},
				opts,
				true
			);
			return parseLedger(json);
		},

		async freezeRules(
			datasetId: string,
			body: { run_id: string; rule_ids: string[] },
			opts: RequestOptions = {}
		): Promise<VerdictFreeze> {
			return parseFreeze(
				await post(`/api/verdict/${encodeURIComponent(datasetId)}/freeze`, body, opts)
			);
		},

		/** Irreversible: the backend refuses a second read. */
		async readHoldout(
			datasetId: string,
			freezeId: string,
			opts: RequestOptions = {}
		): Promise<HoldoutResult> {
			const json = await post(
				`/api/verdict/${encodeURIComponent(datasetId)}/holdout/read`,
				{ freeze_id: freezeId },
				opts
			);
			return parseHoldoutResult(json);
		},

		async getForward(datasetId: string, opts: RequestOptions = {}): Promise<ForwardResult> {
			const json = await request(
				`/api/verdict/${encodeURIComponent(datasetId)}/forward`,
				{},
				opts,
				true
			);
			return parseForward(json);
		},

		async runResearch(body: ResearchRequest, opts: RequestOptions = {}): Promise<ResearchReport> {
			const json = await request(
				'/api/research/run',
				{
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(body)
				},
				{ timeoutMs: 5 * 60_000, ...opts },
				false
			);
			return parseResearch(json);
		}
	};
}

export type ApiClient = ReturnType<typeof createApiClient>;
