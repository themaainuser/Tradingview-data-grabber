import type { ApiClient } from '$lib/api/client';
import type { ResearchReport } from '$lib/api/contracts';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import { createEvaluator } from '$lib/filters/engine';
import { createFilterEditor } from '$lib/filters/edit';
import { newGroup } from '$lib/filters/tree';
import type { EvaluationResult, FilterGroup } from '$lib/filters/types';
import {
	createResearchTable,
	DEFAULT_VISIBLE,
	sortRows,
	type ResearchTable
} from '$lib/research/columns';
import type { LoadStatus } from './datasets.svelte';

const EMPTY = new Uint32Array(0);

export interface RunValidation {
	datasets: string | null;
	feeBps: string | null;
	periodsPerYear: string | null;
}

/**
 * Research runs: the parameter form, the report returned by `POST /api/research/run`, and the
 * filtered/sorted view of its results. The report only ever comes from the backend; before a run
 * the store holds nothing.
 */
export class ResearchStore {
	selectedIds = $state<string[]>([]);
	feeBps = $state(5);
	periodsPerYear = $state(252);
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	report = $state.raw<ResearchReport | null>(null);
	filter = $state<FilterGroup>(newGroup('and'));
	sortKey = $state('forward.sharpe');
	sortDir = $state<'asc' | 'desc'>('desc');
	visibleColumns = $state<string[]>([...DEFAULT_VISIBLE]);
	/** Result ids whose equity curves are overlaid on the chart. */
	compareIds = $state<string[]>([]);
	/** Result shown in the detail panel. */
	activeId = $state<string | null>(null);

	/** The only sanctioned way to mutate `filter`; components call it instead of writing to the tree. */
	readonly filterEditor = createFilterEditor(
		() => this.filter,
		(tree) => (this.filter = tree)
	);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	validation = $derived.by<RunValidation>(() => ({
		datasets:
			this.selectedIds.length === 0
				? 'Select at least one dataset.'
				: this.selectedIds.length > 20
					? 'At most 20 datasets per run.'
					: null,
		feeBps:
			Number.isFinite(this.feeBps) && this.feeBps >= 0 && this.feeBps <= 10_000
				? null
				: 'Fee must be between 0 and 10,000 bps.',
		periodsPerYear:
			Number.isFinite(this.periodsPerYear) && this.periodsPerYear > 0
				? null
				: 'Periods per year must be positive.'
	}));

	canRun = $derived(
		this.status !== 'loading' &&
			this.validation.datasets === null &&
			this.validation.feeBps === null &&
			this.validation.periodsPerYear === null
	);

	table = $derived.by<ResearchTable | null>(() =>
		this.report ? createResearchTable(this.report) : null
	);

	#evaluator = $derived.by(() => (this.table ? createEvaluator(this.table.source) : null));

	evaluation = $derived.by<EvaluationResult | null>(
		() => this.#evaluator?.evaluate(this.filter) ?? null
	);

	/** Row indexes passing the filter, in display order. */
	order = $derived.by<Uint32Array>(() =>
		this.table
			? sortRows(this.table, this.evaluation?.mask ?? null, this.sortKey, this.sortDir)
			: EMPTY
	);

	async run(): Promise<void> {
		if (!this.canRun) return;
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		this.status = 'loading';
		this.error = null;
		try {
			const report = await this.#api.runResearch(
				{
					dataset_ids: [...this.selectedIds],
					fee_bps: this.feeBps,
					periods_per_year: this.periodsPerYear
				},
				{ signal: controller.signal }
			);
			if (controller !== this.#controller) return;
			this.report = report;
			this.compareIds = [];
			this.activeId = null;
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	cancel(): void {
		this.#controller?.abort();
		this.#controller = null;
		if (this.status === 'loading') this.status = this.report ? 'ready' : 'idle';
	}

	open(id: string): void {
		this.activeId = id;
	}

	toggleDataset(id: string): void {
		this.selectedIds = this.selectedIds.includes(id)
			? this.selectedIds.filter((x) => x !== id)
			: [...this.selectedIds, id];
	}

	setSort(key: string): void {
		if (this.sortKey === key) this.sortDir = this.sortDir === 'desc' ? 'asc' : 'desc';
		else {
			this.sortKey = key;
			this.sortDir = this.table?.column(key)?.kind === 'text' ? 'asc' : 'desc';
		}
	}

	toggleColumn(key: string): void {
		this.visibleColumns = this.visibleColumns.includes(key)
			? this.visibleColumns.filter((k) => k !== key)
			: [...this.visibleColumns, key];
	}

	toggleCompare(id: string): void {
		this.compareIds = this.compareIds.includes(id)
			? this.compareIds.filter((x) => x !== id)
			: this.compareIds.length < 6
				? [...this.compareIds, id]
				: this.compareIds;
	}
}
