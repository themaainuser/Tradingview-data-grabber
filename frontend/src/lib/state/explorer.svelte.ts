import type { ApiClient } from '$lib/api/client';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import type { Bars } from '$lib/api/validate';
import { eventStudy, onsetMask, type EventStudy } from '$lib/analysis/event-study';
import { CHART_PALETTE, type ChartPane, type ChartSeries } from '$lib/charts/types';
import { BarSource } from '$lib/explorer/bar-source';
import { uniqueBy } from '$lib/group';
import { conditions, newGroup, nodeId } from '$lib/filters/tree';
import { createEvaluator } from '$lib/filters/engine';
import { createFilterEditor } from '$lib/filters/edit';
import type { Condition, EvaluationResult, FilterGroup } from '$lib/filters/types';
import { getIndicator, resolveParams } from '$lib/indicators';
import type { LoadStatus } from './datasets.svelte';

export interface IndicatorInstance {
	uid: string;
	id: string;
	/** Only the params the user changed; missing keys fall back to registry defaults. */
	params: Record<string, number>;
	visible: boolean;
	colorIndex: number;
}

export interface ChartModel {
	overlays: ChartSeries[];
	panes: ChartPane[];
}

const EMPTY_INDICES = new Uint32Array(0);

/**
 * State of the bar explorer: the open dataset, chart indicators, the compound filter and the
 * values derived from them.
 *
 * Heavy arrays are `$state.raw` (replaced, never mutated) so Svelte does not proxy them. The
 * derived chain is: bars -> source (memoised indicator compute) -> evaluation (vectorised
 * masks, cached per leaf) -> event study. Editing one condition or one indicator parameter
 * therefore recomputes only the affected leaf/indicator.
 */
export class ExplorerStore {
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	bars = $state.raw<Bars | null>(null);
	indicators = $state<IndicatorInstance[]>([]);
	filter = $state<FilterGroup>(newGroup('and'));
	horizons = $state<number[]>([1, 5, 10, 20]);
	onsetOnly = $state(false);
	showVolume = $state(true);
	/** Bar index the chart should centre on; the chart consumes and clears it. */
	focusRequest = $state<{ index: number; nonce: number } | null>(null);

	/** The only sanctioned way to mutate `filter`; components call it instead of writing to the tree. */
	readonly filterEditor = createFilterEditor(
		() => this.filter,
		(tree) => (this.filter = tree)
	);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;
	#colorCursor = 0;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	source = $derived.by(() => (this.bars ? new BarSource(this.bars.columns) : null));

	#evaluator = $derived.by(() => (this.source ? createEvaluator(this.source) : null));

	evaluation = $derived.by<EvaluationResult | null>(
		() => this.#evaluator?.evaluate(this.filter) ?? null
	);

	/** Bars counted as events: filter matches, reduced to run onsets when requested. */
	eventMask = $derived.by<Uint8Array | null>(() => {
		const mask = this.evaluation?.mask ?? null;
		return mask && this.onsetOnly ? onsetMask(mask) : mask;
	});

	/** Matching bar indexes, oldest first. */
	matches = $derived.by<Uint32Array>(() => {
		const mask = this.eventMask;
		if (!mask) return EMPTY_INDICES;
		let count = 0;
		for (let i = 0; i < mask.length; i++) count += mask[i];
		const out = new Uint32Array(count);
		let k = 0;
		for (let i = 0; i < mask.length; i++) if (mask[i] === 1) out[k++] = i;
		return out;
	});

	study = $derived.by<EventStudy | null>(() => {
		if (!this.bars || !this.eventMask) return null;
		return eventStudy(this.bars.columns.close, this.eventMask, this.horizons);
	});

	/** Distinct fields named by enabled conditions: the extra columns of the matches table. */
	referencedFields = $derived.by<string[]>(() => {
		const fields: string[] = [];
		for (const c of conditions(this.filter) as Condition[]) {
			if (!c.enabled || c.field === '') continue;
			fields.push(c.field);
			if (c.rhs) fields.push(c.rhs);
		}
		return uniqueBy(fields, (f) => f);
	});

	chart = $derived.by<ChartModel>(() => {
		const source = this.source;
		const overlays: ChartSeries[] = [];
		const panes: ChartPane[] = [];
		if (!source) return { overlays, panes };
		for (const instance of this.indicators) {
			if (!instance.visible) continue;
			const definition = getIndicator(instance.id);
			if (!definition) continue;
			const params = resolveParams(definition, instance.params);
			const outputs = source.indicator(instance.id, params);
			const args = definition.params.map((p) => params[p.key]).join(', ');
			const series = definition.outputs.map((output, i): ChartSeries => ({
				key: `${instance.uid}:${output.key}`,
				label:
					(args ? `${definition.short}(${args})` : definition.short) +
					(definition.outputs.length > 1 ? ` ${output.label}` : ''),
				color: CHART_PALETTE[(instance.colorIndex + i) % CHART_PALETTE.length],
				values: outputs[i],
				style: output.key.includes('hist') ? 'histogram' : 'line'
			}));
			if (definition.pane === 'price') overlays.push(...series);
			else
				panes.push({
					id: instance.uid,
					label: definition.name,
					series,
					guides: definition.guides ?? []
				});
		}
		return { overlays, panes };
	});

	get hasBars(): boolean {
		return this.bars !== null && this.bars.length > 0;
	}

	async openBackend(id: string): Promise<void> {
		if (this.bars?.id === id && this.status === 'ready') return;
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		this.status = 'loading';
		this.error = null;
		try {
			const bars = await this.#api.getBars(id, { signal: controller.signal });
			if (controller !== this.#controller) return;
			this.#adopt(bars);
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	openLocal(bars: Bars): void {
		this.#controller?.abort();
		this.#controller = null;
		this.error = null;
		this.#adopt(bars);
	}

	#adopt(bars: Bars): void {
		this.bars = bars;
		this.status = 'ready';
		this.focusRequest = null;
	}

	close(): void {
		this.#controller?.abort();
		this.#controller = null;
		this.bars = null;
		this.status = 'idle';
		this.error = null;
	}

	addIndicator(id: string, params: Record<string, number> = {}): string | null {
		if (!getIndicator(id)) return null;
		const uid = nodeId();
		this.indicators.push({
			uid,
			id,
			params,
			visible: true,
			colorIndex: this.#colorCursor++ % CHART_PALETTE.length
		});
		return uid;
	}

	updateIndicator(uid: string, params: Record<string, number>): void {
		const instance = this.indicators.find((i) => i.uid === uid);
		if (instance) instance.params = params;
	}

	removeIndicator(uid: string): void {
		this.indicators = this.indicators.filter((i) => i.uid !== uid);
	}

	toggleIndicator(uid: string): void {
		const instance = this.indicators.find((i) => i.uid === uid);
		if (instance) instance.visible = !instance.visible;
	}

	focusBar(index: number): void {
		this.focusRequest = { index, nonce: (this.focusRequest?.nonce ?? 0) + 1 };
	}
}
