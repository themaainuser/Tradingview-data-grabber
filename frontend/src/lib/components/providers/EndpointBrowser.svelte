<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { ProvidersStore } from '$lib/state/providers.svelte';
	import type { Access } from '$lib/providers/form';
	import PremiumBadge from './PremiumBadge.svelte';

	interface Props {
		store: ProvidersStore;
		onchoose: (endpointId: string) => void;
	}

	let { store, onchoose }: Props = $props();

	const categoryLabel = $derived(
		store.category === 'all'
			? `All categories (${store.counts.all})`
			: (store.categories.find((c) => c.id === store.category)?.title ?? 'All categories')
	);
	const filtered = $derived(
		store.search !== '' || store.category !== 'all' || store.access !== 'all'
	);

	function clear() {
		store.search = '';
		store.category = 'all';
		store.access = 'all';
	}
</script>

<div class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
	<div class="grid gap-3">
		<div class="relative">
			<Search
				class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-muted"
				aria-hidden="true"
			/>
			<Input
				type="search"
				placeholder="Search endpoints"
				aria-label="Search endpoints"
				class="pl-9"
				bind:value={store.search}
			/>
		</div>

		<ToggleGroup.Root
			type="single"
			size="sm"
			value={store.access}
			onValueChange={(v) => v && (store.access = v as Access)}
			aria-label="Access level"
			class="flex-wrap"
		>
			<ToggleGroup.Item value="all">All {store.counts.all}</ToggleGroup.Item>
			<ToggleGroup.Item value="free">Free {store.counts.free}</ToggleGroup.Item>
			<ToggleGroup.Item value="premium" class="text-orange-ink">
				Premium {store.counts.premium}
			</ToggleGroup.Item>
		</ToggleGroup.Root>

		<Select.Root
			type="single"
			value={store.category}
			onValueChange={(v) => (store.category = v || 'all')}
		>
			<Select.Trigger class="w-full" aria-label="Category">{categoryLabel}</Select.Trigger>
			<Select.Content>
				<Select.Item value="all" label="All categories">
					All categories
					<span class="ml-auto type-caption text-ink-muted tabular-nums">{store.counts.all}</span>
				</Select.Item>
				{#each store.categories as category (category.id)}
					<Select.Item value={category.id} label={category.title}>
						{category.title}
						<span class="ml-auto type-caption text-ink-muted tabular-nums">
							{category.shown}{category.shownPremium > 0
								? ` · ${category.shownPremium} premium`
								: ''}
						</span>
					</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
	</div>

	<p class="type-caption text-ink-muted" role="status" data-testid="endpoint-count">
		{store.endpoints.length} endpoint{store.endpoints.length === 1 ? '' : 's'}
	</p>

	{#if store.endpoints.length === 0}
		<div class="grid justify-items-start gap-3 rounded-lg bg-canvas p-4">
			<p class="type-body-sm text-ink-muted">No endpoints match these filters.</p>
			{#if filtered}<Button variant="translucent" size="sm" onclick={clear}>Clear filters</Button
				>{/if}
		</div>
	{:else}
		<ul
			class="grid gap-1 lg:max-h-[min(70svh,720px)] lg:overflow-y-auto lg:pr-1"
			aria-label="Endpoints"
		>
			{#each store.endpoints as e (e.id)}
				{@const active = e.id === store.endpointId}
				<li>
					<button
						type="button"
						onclick={() => onchoose(e.id)}
						aria-current={active ? 'true' : undefined}
						data-premium={e.premium ? 'true' : undefined}
						class="grid w-full gap-1 rounded-lg border-l-2 px-3 py-2.5 text-left transition-colors duration-150 ease-out hover:bg-surface-2 aria-[current=true]:bg-surface-2 {e.premium
							? 'border-orange-ink'
							: 'border-transparent'}"
					>
						<span class="flex flex-wrap items-center gap-x-2 gap-y-1">
							<span class="min-w-0 type-body-sm font-medium">{e.title}</span>
							{#if e.premium}<PremiumBadge />{/if}
						</span>
						{#if e.id !== e.title}
							<span class="font-mono type-micro text-ink-muted">{e.id}</span>
						{/if}
						<span class="line-clamp-2 type-caption text-ink-muted">{e.summary}</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
