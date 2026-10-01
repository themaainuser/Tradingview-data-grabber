import { createContext } from 'svelte';
import { createApiClient, type ApiClient } from '$lib/api/client';
import { ChartsStore } from './charts.svelte';
import { DatasetsStore } from './datasets.svelte';
import type { ExplorerStore } from './explorer.svelte';
import { ProvidersStore } from './providers.svelte';
import { ResearchStore } from './research.svelte';
import { SavedFilters } from './saved-filters.svelte';
import { SentimentStore } from './sentiment.svelte';
import { ThemeStore } from './theme.svelte';
import { VerdictStore } from './verdict.svelte';

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
	readonly charts: ChartsStore;
	readonly research: ResearchStore;
	readonly sentiment: SentimentStore;
	readonly verdict: VerdictStore;
	readonly providers: ProvidersStore;
	readonly explorerFilters = new SavedFilters('explorer');
	/** Created here but wired to the browser by `theme.attach()` in the root layout. */
	readonly theme = new ThemeStore();
	readonly researchFilters = new SavedFilters('research');

	constructor(api: ApiClient = createApiClient()) {
		this.api = api;
		this.datasets = new DatasetsStore(api);
		this.charts = new ChartsStore(api);
		this.research = new ResearchStore(api);
		this.sentiment = new SentimentStore(api);
		this.verdict = new VerdictStore(api);
		this.providers = new ProvidersStore(api);
	}
}

export const [getApp, setApp] = createContext<AppState>();
