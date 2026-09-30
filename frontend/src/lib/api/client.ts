import { ApiError, toApiError } from './errors';
import type {
	ChartsResponse,
	CorrelationResponse,
	DatasetSummary,
	FearGreedResponse,
	ResearchReport,
	ResearchRequest
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
