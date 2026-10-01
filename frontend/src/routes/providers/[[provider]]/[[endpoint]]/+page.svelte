<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ExternalIcon from '@lucide/svelte/icons/external-link';
	import KeyRound from '@lucide/svelte/icons/key-round';
	import PlugZap from '@lucide/svelte/icons/plug-zap';
	import { Badge } from '$lib/components/ui/badge';
	import * as Select from '$lib/components/ui/select';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import EndpointBrowser from '$lib/components/providers/EndpointBrowser.svelte';
	import ParamForm from '$lib/components/providers/ParamForm.svelte';
	import ExternalLink from '$lib/components/providers/ExternalLink.svelte';
	import PremiumBadge from '$lib/components/providers/PremiumBadge.svelte';
	import ResultPanel from '$lib/components/providers/ResultPanel.svelte';
	import { premiumLabel } from '$lib/providers/form';
	import { getApp } from '$lib/state/app.svelte';

	const { providers } = getApp();

	onMount(() => {
		void providers.loadProviders();
	});

	const providerParam = $derived(page.params.provider ?? null);
	const endpointParam = $derived(page.params.endpoint ?? null);
	const ROUTE = '/providers/[[provider]]/[[endpoint]]' as const;

	function go(provider: string, endpoint: string | null, replace = false) {
		const path = endpoint ? resolve(ROUTE, { provider, endpoint }) : resolve(ROUTE, { provider });
		void goto(path, { replaceState: replace, keepFocus: true, noScroll: true });
	}

	// URL -> store, once the provider list is known. Opening a provider or endpoint never fetches data.
	$effect(() => {
		const list = providers.status === 'ready' ? providers.providers : null;
		const requestedProvider = providerParam;
		const requestedEndpoint = endpointParam;
		if (!list) return;
		untrack(() => {
			if (!requestedProvider) {
				if (list[0]) go(list[0].id, null, true);
				return;
			}
			if (!list.some((p) => p.id === requestedProvider)) providers.select(null, null);
			else providers.select(requestedProvider, requestedEndpoint);
		});
	});

	function choose(endpointId: string) {
		if (!providers.providerId) return;
		go(providers.providerId, endpointId);
		// On a narrow screen the form is below the list; bring it into view.
		if (window.matchMedia('(max-width: 1023px)').matches) {
			document.getElementById('endpoint-detail')?.scrollIntoView({ block: 'start' });
		}
	}

	const provider = $derived(providers.provider);
	const endpoint = $derived(providers.endpoint);
	const unknownProvider = $derived(
		providers.status === 'ready' &&
			providerParam !== null &&
			!providers.providers.some((p) => p.id === providerParam)
	);
	const unknownEndpoint = $derived(
		providers.catalogStatus === 'ready' && endpointParam !== null && !endpoint
	);
</script>

<svelte:head>
	<title>Providers · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-10">
	<header class="grid max-w-[860px] gap-5">
		<p class="type-caption text-ink-muted">External market data</p>
		<h1 class="type-display-lg">Providers</h1>
		<p class="max-w-[60ch] type-body-lg text-ink-muted">
			Browse everything a data provider documents, fetch it through the backend and see what it
			shows. Nothing is requested until you press Fetch, and nothing is ever made up: if the
			provider refuses or has no data, the page says so.
		</p>
		<Select.Root
			type="single"
			value={providerParam ?? ''}
			onValueChange={(id) => id && go(id, null)}
			disabled={providers.providers.length === 0}
		>
			<Select.Trigger class="w-72" aria-label="Data provider">
				{provider?.name ??
					(providers.status === 'loading' ? 'Loading providers…' : 'Choose a provider')}
			</Select.Trigger>
			<Select.Content>
				{#each providers.providers as p (p.id)}
					<Select.Item value={p.id} label={p.name}>
						{p.name}
						<span class="ml-auto type-caption text-ink-muted"
							>{p.configured ? 'Key set' : 'No key'}</span
						>
					</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
	</header>

	{#if providers.status === 'error' && providers.error}
		<ErrorPanel
			error={providers.error}
			title="Could not load the providers"
			onretry={() => providers.loadProviders()}
		/>
	{:else if providers.status !== 'ready'}
		<div class="grid gap-4" role="status" aria-live="polite">
			<span class="sr-only">Loading providers…</span>
			<Skeleton class="h-28 w-full rounded-xl" />
			<Skeleton class="h-96 w-full rounded-xl" />
		</div>
	{:else if providers.providers.length === 0}
		<EmptyState
			icon={PlugZap}
			title="No providers are registered"
			description="The backend did not list any data providers."
		/>
	{:else if unknownProvider}
		<EmptyState
			icon={PlugZap}
			title="Provider not found"
			description="There is no provider with this address. Choose one from the list above."
		/>
	{:else if provider}
		<section
			aria-label="About {provider.name}"
			class="grid grid-cols-[minmax(0,1fr)] gap-4 rounded-xl bg-surface-1 p-5"
		>
			<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
				<h2 class="type-headline">{provider.name}</h2>
				{#if provider.configured}
					<Badge variant="success" data-testid="key-status"
						><KeyRound aria-hidden="true" /> API key set</Badge
					>
				{:else}
					<Badge variant="destructive" data-testid="key-status"
						><KeyRound aria-hidden="true" /> No API key</Badge
					>
				{/if}
				<span class="type-caption text-ink-muted tabular-nums" data-testid="provider-counts">
					{provider.endpoint_count} endpoints ·
					<span class="text-orange-ink">{provider.premium_count} premium</span>
				</span>
				<ExternalLink
					href={provider.docs_url}
					class="ml-auto inline-flex items-center gap-1.5 type-body-sm"
				>
					Documentation <ExternalIcon class="size-3.5" aria-hidden="true" />
				</ExternalLink>
			</div>
			<p class="max-w-[72ch] type-body text-pretty text-ink-muted">{provider.description}</p>
			<p class="max-w-[72ch] type-body-sm text-pretty text-ink-muted" data-testid="limits-note">
				{provider.limits_note}
				<span class="tabular-nums"
					>This session: {provider.requests_this_session} request{provider.requests_this_session ===
					1
						? ''
						: 's'} sent.</span
				>
			</p>
			{#if providers.plans.length > 0}
				<div class="grid gap-2" data-testid="plans">
					<h3 class="type-subhead">Plans</h3>
					<p class="max-w-[72ch] type-caption text-pretty text-ink-muted">
						Each premium endpoint names the cheapest plan that includes it. The provider decides
						what your key may use: a plan that lacks an endpoint is refused when you fetch.
					</p>
					<ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-4" aria-label="Subscription plans">
						{#each providers.plans as plan (plan.name)}
							<li
								data-plan={plan.name}
								data-premium={plan.premium ? 'true' : undefined}
								class="grid content-start gap-1 rounded-lg border-l-2 bg-canvas p-3 {plan.premium
									? 'border-orange-ink'
									: 'border-transparent'}"
							>
								<span class="flex flex-wrap items-center gap-2">
									<span class="type-body-sm font-medium">{plan.name}</span>
									{#if plan.premium}<PremiumBadge />{/if}
								</span>
								<span class="type-caption text-ink-muted tabular-nums"
									>{plan.count} endpoint{plan.count === 1 ? '' : 's'} start{plan.count === 1
										? 's'
										: ''} here</span
								>
								<span class="type-caption text-pretty text-ink-muted">{plan.summary}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if !provider.configured}
				<p
					class="max-w-[72ch] rounded-lg bg-canvas p-3 type-body-sm text-pretty"
					role="status"
					data-testid="key-help"
				>
					Set <code class="font-mono text-ink">{provider.key_env}</code> in the backend's
					environment or
					<code class="font-mono text-ink">.env</code> file and restart it. The key stays on the
					server; this page never sees it. You can browse every endpoint without one.
					{#if provider.key_url}<ExternalLink href={provider.key_url}>Get a key</ExternalLink>.{/if}
				</p>
			{/if}
		</section>

		{#if providers.catalogStatus === 'error' && providers.catalogError}
			<ErrorPanel
				error={providers.catalogError}
				title="Could not load the endpoint catalog"
				onretry={() => providers.providerId && providers.loadCatalog(providers.providerId)}
			/>
		{:else if !providers.catalog}
			<div class="grid gap-4" role="status" aria-live="polite">
				<span class="sr-only">Loading the endpoint catalog…</span>
				<Skeleton class="h-96 w-full rounded-xl" />
			</div>
		{:else}
			<div
				class="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[340px_minmax(0,1fr)] lg:items-start"
			>
				<aside
					aria-label="Endpoints"
					class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4 lg:sticky lg:top-[72px]"
				>
					<h2 class="type-headline">Endpoints</h2>
					<p class="type-caption text-pretty text-ink-muted">
						Premium endpoints carry the <PremiumBadge class="mx-0.5 align-middle" /> badge and an orange
						edge. A free key is refused by them.
					</p>
					<EndpointBrowser store={providers} onchoose={choose} />
				</aside>

				<div id="endpoint-detail" class="grid min-w-0 scroll-mt-20 grid-cols-[minmax(0,1fr)] gap-8">
					{#if unknownEndpoint}
						<EmptyState
							icon={PlugZap}
							title="Endpoint not found"
							description="This provider has no endpoint with that name. Choose one from the list."
						/>
					{:else if !endpoint}
						<EmptyState
							icon={PlugZap}
							title="Choose an endpoint"
							description="Pick an endpoint from the list to see its parameters. Choosing one does not contact the provider."
						/>
					{:else}
						<section
							aria-labelledby="endpoint-title"
							class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-5 rounded-xl bg-surface-1 p-5 {endpoint.premium
								? 'border-l-2 border-orange-ink'
								: ''}"
							data-testid="endpoint-detail"
						>
							<header class="grid gap-2">
								<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
									<h2 id="endpoint-title" class="type-headline">{endpoint.title}</h2>
									{#if endpoint.premium}<PremiumBadge label={premiumLabel(endpoint)} />{:else}<Badge
											variant="secondary">Free</Badge
										>{/if}
									{#if endpoint.trending}<Badge variant="secondary">Popular</Badge>{/if}
								</div>
								<p class="font-mono type-caption text-ink-muted">{endpoint.id}</p>
								<p class="max-w-[72ch] type-body text-pretty text-ink-muted">
									{endpoint.description}
								</p>
								<ExternalLink
									href={endpoint.doc_url}
									class="inline-flex w-fit items-center gap-1.5 type-body-sm"
								>
									Read the documentation <ExternalIcon class="size-3.5" aria-hidden="true" />
								</ExternalLink>
							</header>

							{#if endpoint.premium}
								<div
									class="grid gap-2 rounded-lg bg-orange-ink/10 p-4"
									role="note"
									data-testid="premium-callout"
								>
									<p class="type-body-sm font-medium text-orange-ink">Premium endpoint</p>
									<p
										class="max-w-[68ch] type-body-sm text-pretty"
										data-testid="premium-callout-text"
									>
										{#if endpoint.plan}
											This endpoint is included from the <strong>{endpoint.plan}</strong> plan. A key
											on a lower plan is refused by the provider, and nothing is shown in its place. If
											your plan includes it, fetch as normal.
										{:else}
											This endpoint needs a paid {provider.name} plan. With a free key the provider refuses
											it, and nothing is shown in its place. If your key is premium, fetch as normal.
										{/if}
									</p>
									{#each endpoint.premium_notes as note (note)}
										<p class="max-w-[68ch] type-caption text-pretty text-ink-muted">{note}</p>
									{/each}
								</div>
							{:else if endpoint.params.some((p) => p.premium_note)}
								<p
									class="max-w-[68ch] rounded-lg bg-orange-ink/10 p-4 type-body-sm text-pretty"
									role="note"
									data-testid="premium-options-callout"
								>
									<span class="font-medium text-orange-ink"
										>Free endpoint with premium options.</span
									>
									The options marked <span class="text-orange-ink">Premium option</span> below need a
									paid plan.
								</p>
							{/if}

							<ParamForm store={providers} />
						</section>

						<ResultPanel store={providers} />
					{/if}
				</div>
			</div>
		{/if}
	{/if}
</div>
