import type { ApiClient } from '$lib/api/client';
import type { ChartsResponse, CorrelationResponse } from '$lib/api/contracts';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import type { LoadStatus } from './datasets.svelte';

export type ActivityMetric = 'volume' | 'range_pct' | 'return_pct';

export const PROFILE_BINS = [30, 60, 100] as const;
export const VOLATILITY_WINDOWS = [10, 30, 60, 100] as const;

/** Correlation needs at least two datasets and the backend accepts at most twenty. */
export const MAX_CORRELATION = 20;

/**
 * The Charts page: analysis computed by the backend for one dataset (volume profile, return
 * distribution, drawdown, rolling volatility, activity and seasonality) plus a correlation matrix
 * across several. Everything is fetched from `/api/*`; before a dataset is opened the store holds
 * nothing, and sections the backend could not compute arrive as null with a reason.
 */
export class ChartsStore {
	datasetId = $state<string | null>(null);
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	charts = $state.raw<ChartsResponse | null>(null);

	bins = $state<number>(60);
	window = $state<number>(30);
	activityMetric = $state<ActivityMetric>('range_pct');

	correlationIds = $state<string[]>([]);
	correlationStatus = $state<LoadStatus>('idle');
	correlationError = $state.raw<ApiError | null>(null);
	correlation = $state.raw<CorrelationResponse | null>(null);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;
	#correlationController: AbortController | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	/** Opens a dataset (or re-fetches it after a parameter change). A newer request supersedes an older one. */
	async open(id: string): Promise<void> {
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		this.datasetId = id;
		this.status = 'loading';
		this.error = null;
		try {
			const charts = await this.#api.getCharts(id, {
				bins: this.bins,
				window: this.window,
				signal: controller.signal
			});
			if (controller !== this.#controller) return;
			this.charts = charts;
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	reload(): Promise<void> {
		return this.datasetId ? this.open(this.datasetId) : Promise.resolve();
	}

	setBins(bins: number): Promise<void> {
		this.bins = bins;
		return this.reload();
	}

	setWindow(window: number): Promise<void> {
		this.window = window;
		return this.reload();
	}

	toggleCorrelation(id: string): Promise<void> {
		this.correlationIds = this.correlationIds.includes(id)
			? this.correlationIds.filter((x) => x !== id)
			: this.correlationIds.length < MAX_CORRELATION
				? [...this.correlationIds, id]
				: this.correlationIds;
		return this.loadCorrelation();
	}

	async loadCorrelation(): Promise<void> {
		this.#correlationController?.abort();
		if (this.correlationIds.length < 2) {
			this.#correlationController = null;
			this.correlation = null;
			this.correlationError = null;
			this.correlationStatus = 'idle';
			return;
		}
		const controller = (this.#correlationController = new AbortController());
		this.correlationStatus = 'loading';
		this.correlationError = null;
		try {
			const result = await this.#api.getCorrelation(this.correlationIds, {
				signal: controller.signal
			});
			if (controller !== this.#correlationController) return;
			this.correlation = result;
			this.correlationStatus = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#correlationController) return;
			// Keep no stale matrix: it would describe a different selection than the one shown.
			this.correlation = null;
			this.correlationError = toApiError(error);
			this.correlationStatus = 'error';
		}
	}

	/** Drops everything, e.g. when the selected dataset disappears from the backend listing. */
	reset(): void {
		this.#controller?.abort();
		this.#correlationController?.abort();
		this.datasetId = null;
		this.charts = null;
		this.status = 'idle';
		this.error = null;
		this.correlationIds = [];
		this.correlation = null;
		this.correlationStatus = 'idle';
		this.correlationError = null;
	}
}
