<script lang="ts">
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Info from '@lucide/svelte/icons/info';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import { formatBytes } from '$lib/format';
	import { formatTimestamp } from '$lib/providers/format';
	import { credentialNames, quotaText } from '$lib/providers/form';
	import { statusCopy } from '$lib/providers/status';
	import type { ProvidersStore } from '$lib/state/providers.svelte';
	import PremiumBadge from './PremiumBadge.svelte';
	import ViewRenderer from './views/ViewRenderer.svelte';

	let { store }: { store: ProvidersStore } = $props();

	const result = $derived(store.result);
	const name = $derived(store.provider?.name ?? 'the provider');
	const copy = $derived(
		result && result.status !== 'ok'
			? statusCopy(
					result.status,
					store.provider ? credentialNames(store.provider) : 'the API key variable'
				)
			: null
	);
	const sent = $derived(
		result
			? Object.entries(result.params)
					.map(([k, v]) => (Array.isArray(v) ? v.map((x) => `${k}=${x}`).join('&') : `${k}=${v}`))
					.join('&')
			: ''
	);

	let rawOpen = $state(false);
	const rawText = $derived(
		rawOpen && result?.raw != null ? JSON.stringify(result.raw, null, 2) : ''
	);
</script>

<section
	aria-labelledby="result-title"
	class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-5"
	data-testid="result"
>
	<h2 id="result-title" class="type-headline">Result</h2>

	{#if store.loading}
		<div class="grid gap-3" role="status" aria-live="polite">
			<p class="type-body-sm text-ink-muted">Fetching from {name}…</p>
			<Skeleton class="h-56 w-full rounded-xl" />
			<Skeleton class="h-32 w-full rounded-xl" />
		</div>
	{:else if store.queryError}
		<ErrorPanel error={store.queryError} title="The request failed" />
	{:else if !result}
		<div class="flex items-start gap-3 rounded-xl bg-surface-1 p-5" data-testid="not-fetched">
			<Info class="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden="true" />
			<p class="max-w-[62ch] type-body text-pretty text-ink-muted">
				Nothing has been fetched yet. Opening a provider or an endpoint never contacts it; press
				<strong class="font-medium text-ink">Fetch data</strong> to make one request.
			</p>
		</div>
	{:else if copy}
		<div
			role="alert"
			data-testid="status-notice"
			data-status={result.status}
			class="grid gap-3 rounded-xl bg-surface-1 p-5 {copy.tone === 'premium'
				? 'border-l-2 border-orange-ink'
				: ''}"
		>
			<div class="flex flex-wrap items-center gap-3">
				{#if copy.tone === 'premium'}<PremiumBadge />{:else}<TriangleAlert
						class="size-4 shrink-0 {copy.tone === 'error' ? 'text-coral-ink' : 'text-ink-muted'}"
						aria-hidden="true"
					/>{/if}
				<h3 class="type-subhead">{copy.title}</h3>
			</div>
			<p class="max-w-[68ch] type-body text-pretty text-ink-muted">{copy.advice}</p>
			{#if result.message}
				<p
					class="max-w-[68ch] rounded-lg bg-canvas p-3 type-body-sm text-pretty break-words"
					data-testid="provider-message"
				>
					<span class="text-ink-muted">{name} says:</span>
					{result.message}
				</p>
			{/if}
		</div>
	{:else}
		<div class="flex flex-wrap items-center justify-between gap-3">
			<p class="type-caption text-ink-muted" data-testid="result-meta">
				{#if result.fetched_at}Fetched {formatTimestamp(result.fetched_at)}{/if}
				{result.cached ? ' · served from cache (no request used)' : ''}
				· {result.elapsed_ms.toLocaleString('en-US')} ms · {formatBytes(result.bytes)}
			</p>
			<Button
				variant="translucent"
				size="sm"
				onclick={() => store.fetchFresh()}
				disabled={!store.canFetch}
			>
				<RefreshCw aria-hidden="true" /> Fetch again (uses {store.requestCost === 1
					? 'a request'
					: quotaText(store.requestCost)})
			</Button>
		</div>
		<p
			class="rounded-lg bg-surface-1 p-3 type-caption break-all text-ink-muted"
			data-testid="sent-params"
		>
			Request sent: <code class="font-mono text-ink">{sent}</code>
		</p>

		{#if result.notes.length}
			<ul
				class="grid gap-1 rounded-lg bg-surface-1 p-3 type-caption text-ink-muted"
				data-testid="notes"
			>
				{#each result.notes as note (note)}<li>{note}</li>{/each}
			</ul>
		{/if}

		{#each result.views as view (view.id)}
			<ViewRenderer {view} />
		{/each}

		<Collapsible.Root bind:open={rawOpen}>
			<Collapsible.Trigger
				class="group/raw flex items-center gap-2 rounded-md type-body-sm text-ink-muted hover:text-ink"
			>
				Raw response
				<ChevronDown
					class="size-4 transition-transform duration-150 ease-out group-data-[state=open]/raw:rotate-180"
					aria-hidden="true"
				/>
			</Collapsible.Trigger>
			<Collapsible.Content>
				{#if result.raw_omitted}
					<p class="mt-3 type-caption text-ink-muted" data-testid="raw-omitted">
						{result.raw_omitted.reason} ({formatBytes(result.raw_omitted.bytes)})
					</p>
				{:else if result.raw != null}
					<!-- A scrollable region must be reachable by keyboard. -->
					<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
					<pre
						class="mt-3 max-h-96 overflow-auto rounded-lg bg-surface-1 p-4 type-caption text-ink"
						tabindex="0"
						aria-label="Raw response">{rawText}</pre>
				{/if}
			</Collapsible.Content>
		</Collapsible.Root>
	{/if}
</section>
