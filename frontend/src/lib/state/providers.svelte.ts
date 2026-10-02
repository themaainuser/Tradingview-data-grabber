import type { ApiClient } from '$lib/api/client';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import type {
	Catalog,
	CatalogEndpoint,
	ParamValue,
	ParamValues,
	ProviderSummary,
	QueryResponse
} from '$lib/api/providers';
import {
	accessCounts,
	buildPayload,
	categoryCounts,
	credentialNames,
	filterEndpoints,
	planCounts,
	seedValues,
	validateParams,
	valuesFromExample,
	type Access
} from '$lib/providers/form';
import type { LoadStatus } from './datasets.svelte';

/**
 * The Providers page: the provider list, one provider's catalog, the form for one endpoint and the
 * result of a query.
 *
 * A query is made only by `fetch()`: opening a provider, choosing an endpoint or loading a catalog
 * never reaches the provider, because providers meter requests (Alpha Vantage free keys get 25 a
 * day). Choosing another provider or endpoint clears the previous result so one provider's data is
 * never shown under another's name.
 */
export class ProvidersStore {
	providers = $state.raw<ProviderSummary[]>([]);
	status = $state<LoadStatus>('idle');
	error = $state.raw<ApiError | null>(null);

	providerId = $state<string | null>(null);
	endpointId = $state<string | null>(null);
	catalogs = $state.raw<Record<string, Catalog>>({});
	catalogStatus = $state<LoadStatus>('idle');
	catalogError = $state.raw<ApiError | null>(null);

	forms = $state<Record<string, ParamValues>>({});
	search = $state('');
	category = $state('all');
	access = $state<Access>('all');

	queryStatus = $state<LoadStatus>('idle');
	queryError = $state.raw<ApiError | null>(null);
	result = $state.raw<QueryResponse | null>(null);

	readonly #api: ApiClient;
	#queryController: AbortController | null = null;
	#listController: AbortController | null = null;

	constructor(api: ApiClient) {
		this.#api = api;
	}

	provider = $derived(this.providers.find((p) => p.id === this.providerId) ?? null);
	catalog = $derived(this.providerId ? (this.catalogs[this.providerId] ?? null) : null);
	endpoint = $derived<CatalogEndpoint | null>(
		this.catalog?.endpoints.find((e) => e.id === this.endpointId) ?? null
	);
	filters = $derived({ search: this.search, category: this.category, access: this.access });
	endpoints = $derived(this.catalog ? filterEndpoints(this.catalog.endpoints, this.filters) : []);
	counts = $derived(
		this.catalog
			? accessCounts(this.catalog.endpoints, this.filters)
			: { all: 0, free: 0, premium: 0 }
	);
	categories = $derived(
		this.catalog
			? categoryCounts(this.catalog.endpoints, this.catalog.categories, this.filters)
			: []
	);

	formKey = $derived(
		this.providerId && this.endpointId ? `${this.providerId}/${this.endpointId}` : null
	);
	values = $derived<ParamValues>((this.formKey && this.forms[this.formKey]) || {});
	errors = $derived<Record<string, string>>(
		this.endpoint ? validateParams(this.endpoint, this.values) : {}
	);
	configured = $derived(this.provider?.configured ?? false);
	requestCost = $derived(this.endpoint?.request_cost ?? 1);
	plans = $derived(
		this.provider && this.catalog ? planCounts(this.provider.plans, this.catalog.endpoints) : []
	);
	loading = $derived(this.queryStatus === 'loading');
	canFetch = $derived(
		!!this.endpoint && this.configured && Object.keys(this.errors).length === 0 && !this.loading
	);
	/** Why Fetch is unavailable, in words; null when it is available. */
	blockedReason = $derived.by(() => {
		if (!this.endpoint) return 'Choose an endpoint first.';
		if (!this.configured && this.provider)
			return `Set ${credentialNames(this.provider)} on the backend to fetch.`;
		if (Object.keys(this.errors).length > 0) return 'Fix the highlighted fields first.';
		return null;
	});

	async loadProviders(): Promise<void> {
		this.#listController?.abort();
		const controller = (this.#listController = new AbortController());
		this.status = 'loading';
		this.error = null;
		try {
			const providers = await this.#api.listProviders({ signal: controller.signal });
			if (controller !== this.#listController) return;
			this.providers = providers;
			this.status = 'ready';
		} catch (error) {
			if (isAbort(error) || controller !== this.#listController) return;
			this.error = toApiError(error);
			this.status = 'error';
		}
	}

	/** Applies the URL: which provider and endpoint are open. Never fetches data from the provider. */
	select(providerId: string | null, endpointId: string | null): void {
		const providerChanged = providerId !== this.providerId;
		const changed = providerChanged || endpointId !== this.endpointId;
		this.providerId = providerId;
		this.endpointId = endpointId;
		if (changed) {
			this.#queryController?.abort();
			this.#queryController = null;
			this.result = null;
			this.queryStatus = 'idle';
			this.queryError = null;
		}
		if (providerChanged) {
			this.search = '';
			this.category = 'all';
			this.access = 'all';
			this.catalogError = null;
			this.catalogStatus = providerId && this.catalogs[providerId] ? 'ready' : 'idle';
			if (providerId && !this.catalogs[providerId]) void this.loadCatalog(providerId);
		}
		this.#seed();
	}

	async loadCatalog(providerId: string): Promise<void> {
		this.catalogStatus = 'loading';
		this.catalogError = null;
		try {
			const catalog = await this.#api.getProviderCatalog(providerId);
			this.catalogs = { ...this.catalogs, [providerId]: catalog };
			if (this.providerId === providerId) {
				this.catalogStatus = 'ready';
				this.#seed();
			}
		} catch (error) {
			if (isAbort(error) || this.providerId !== providerId) return;
			this.catalogError = toApiError(error);
			this.catalogStatus = 'error';
		}
	}

	#seed(): void {
		const key = this.formKey;
		if (key && this.endpoint && !this.forms[key])
			this.forms = { ...this.forms, [key]: seedValues(this.endpoint) };
	}

	setValue(name: string, value: ParamValue): void {
		const key = this.formKey;
		if (key) this.forms = { ...this.forms, [key]: { ...this.forms[key], [name]: value } };
	}

	addEntry(name: string): void {
		const current = this.values[name];
		this.setValue(name, [...(Array.isArray(current) ? current : current ? [current] : []), '']);
	}

	removeEntry(name: string, index: number): void {
		const current = this.values[name];
		const next = (Array.isArray(current) ? current : []).filter((_, i) => i !== index);
		this.setValue(name, next.length ? next : ['']);
	}

	/** Fills the form from one of the documentation's examples. Does not fetch. */
	applyExample(index: number): void {
		const key = this.formKey;
		const example = this.endpoint?.examples[index];
		if (key && this.endpoint && example) {
			this.forms = { ...this.forms, [key]: valuesFromExample(this.endpoint, example.params) };
		}
	}

	/** Fetches the open endpoint. Ignored while a query is in flight or the form is not valid. */
	async fetch(refresh = false): Promise<void> {
		const providerId = this.providerId;
		const endpoint = this.endpoint;
		if (!providerId || !endpoint || !this.canFetch) return;
		const controller = (this.#queryController = new AbortController());
		this.queryStatus = 'loading';
		this.queryError = null;
		try {
			const result = await this.#api.queryProvider(
				providerId,
				{ endpoint: endpoint.id, params: buildPayload(endpoint, this.values), refresh },
				{ signal: controller.signal }
			);
			if (controller !== this.#queryController) return;
			this.result = result;
			this.queryStatus = 'ready';
			void this.#refreshCount();
		} catch (error) {
			if (isAbort(error) || controller !== this.#queryController) return;
			this.queryError = toApiError(error);
			this.result = null;
			this.queryStatus = 'error';
		}
	}

	fetchFresh(): Promise<void> {
		return this.fetch(true);
	}

	/** Keeps "requests this session" honest after a query, without a loading state. */
	async #refreshCount(): Promise<void> {
		try {
			this.providers = await this.#api.listProviders();
		} catch {
			// The count is informational; the next load corrects it.
		}
	}
}
