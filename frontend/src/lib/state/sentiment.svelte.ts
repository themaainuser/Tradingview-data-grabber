import type { ApiClient } from '$lib/api/client';
import type { FearGreedResponse } from '$lib/api/contracts';
import { ApiError, isAbort, toApiError } from '$lib/api/errors';
import {
	RANGES,
	rangeStart,
	rangeSummary,
	zoneCounts,
	type RangeKey,
	type RangeSummary,
	type ZoneShare
} from '$lib/sentiment/stats';
import type { LoadStatus } from './datasets.svelte';

/** Columns of the visible window, ready for the chart. */
export interface SentimentView {
	time: number[];
	score: number[];
	price: (number | null)[];
}

/**
 * The Fear & Greed page: the index fetched by the backend from CoinMarketCap, plus the range and
 * overlay choices. `data` stays null until the backend has real readings; there is no fallback.
 * A failed refresh keeps the previous readings on screen and surfaces the error beside them.
 */
export class SentimentStore {
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	data = $state.raw<FearGreedResponse | null>(null);
	range = $state<RangeKey>('90d');
	showPrice = $state(true);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	start = $derived.by(() => {
		if (!this.data) return 0;
		const days = RANGES.find((r) => r.key === this.range)?.days ?? null;
		return rangeStart(this.data.points.time, days);
	});

	/** Readings inside the selected range. */
	view = $derived.by<SentimentView | null>(() => {
		if (!this.data) return null;
		const { time, score, btc_price } = this.data.points;
		return {
			time: time.slice(this.start),
			score: score.slice(this.start),
			price: btc_price.slice(this.start)
		};
	});

	zones = $derived.by<ZoneShare[]>(() =>
		this.data ? zoneCounts(this.data.points.score, this.start, this.data.bands) : []
	);

	summary = $derived.by<RangeSummary | null>(() =>
		this.data ? rangeSummary(this.data.points.time, this.data.points.score, this.start) : null
	);

	/** True when any reading in the range carries a Bitcoin price, so the overlay has something to draw. */
	hasPrice = $derived(this.view?.price.some((p) => p !== null) ?? false);

	async load(): Promise<void> {
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		this.status = 'loading';
		this.error = null;
		try {
			const data = await this.#api.getFearGreed({ signal: controller.signal });
			if (controller !== this.#controller) return;
			this.data = data;
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			const apiError = toApiError(error);
			// A 404 means this backend predates the endpoint; say so instead of the bare "Not Found".
			this.error =
				apiError.status === 404
					? new ApiError(
							'http',
							'This backend does not serve the Fear & Greed index. Update it and restart `tvdata serve`.',
							404
						)
					: apiError;
			this.status = 'error';
		}
	}
}
