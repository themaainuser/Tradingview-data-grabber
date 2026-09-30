import { createContext } from 'svelte';
import { createApiClient, type ApiClient } from '$lib/api/client';
import { DatasetsStore } from './datasets.svelte';
import type { ExplorerStore } from './explorer.svelte';
import { ResearchStore } from './research.svelte';
import { SavedFilters } from './saved-filters.svelte';

/**
 * Root of the application state, created once in the root layout and shared through Svelte
 * context (never a module singleton, so state cannot leak between mounts or tests).
 */
export class AppState {
	readonly api: ApiClient;
	readonly datasets: DatasetsStore;
	/**
	 * Created by the explorer route on first visit. The store pulls in the whole indicator
	 * library, so keeping construction there keeps that code out of the initial bundle.
	 */
	explorer: ExplorerStore | null = null;
	readonly research: ResearchStore;
	readonly explorerFilters = new SavedFilters('explorer');
	readonly researchFilters = new SavedFilters('research');

	constructor(api: ApiClient = createApiClient()) {
		this.api = api;
		this.datasets = new DatasetsStore(api);
		this.research = new ResearchStore(api);
	}
}

export const [getApp, setApp] = createContext<AppState>();
