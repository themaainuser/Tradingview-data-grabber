import type { ApiClient } from '$lib/api/client';
import type { DatasetSummary } from '$lib/api/contracts';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import type { Bars } from '$lib/api/validate';
import { importCsvFile } from '$lib/data/csv';

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';

/**
 * Datasets available to the dashboard.
 *
 * `items` mirrors the backend's data directory exactly (an empty backend yields an empty list;
 * nothing is ever fabricated). `local` holds files the user imported in this tab: they live in
 * memory only and can be explored but not sent to the backend research run.
 */
export class DatasetsStore {
	items = $state.raw<DatasetSummary[]>([]);
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);
	local = $state.raw<Bars[]>([]);
	importError = $state<string | null>(null);

	readonly #api: ApiClient;
	#controller: AbortController | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	/** Datasets the backend could parse; invalid files stay listed but cannot be opened. */
	usable = $derived(this.items.filter((d) => d.valid));

	async load(): Promise<void> {
		this.#controller?.abort();
		const controller = (this.#controller = new AbortController());
		this.status = 'loading';
		this.error = null;
		try {
			const items = await this.#api.listDatasets({ signal: controller.signal });
			if (controller !== this.#controller) return;
			this.items = items;
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#controller) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	async importFile(file: File): Promise<Bars | null> {
		this.importError = null;
		try {
			const bars = await importCsvFile(file);
			this.local = [...this.local, bars];
			return bars;
		} catch (error) {
			this.importError = error instanceof Error ? error.message : String(error);
			return null;
		}
	}

	dismissImportError(): void {
		this.importError = null;
	}

	removeLocal(id: string): void {
		this.local = this.local.filter((b) => b.id !== id);
	}

	findLocal(id: string): Bars | undefined {
		return this.local.find((b) => b.id === id);
	}

	get isEmpty(): boolean {
		return this.status === 'ready' && this.items.length === 0 && this.local.length === 0;
	}
}
