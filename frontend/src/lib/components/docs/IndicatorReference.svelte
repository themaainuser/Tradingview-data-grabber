<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import { INDICATORS } from '$lib/indicators';
	import { INDICATOR_CATEGORIES, type IndicatorCategory } from '$lib/indicators/types';
	import { groupBy } from '$lib/group';

	let query = $state('');
	let category = $state<'all' | IndicatorCategory>('all');

	// Filtering is a pure derivation over a static list of ~130 entries; no debounce needed.
	const results = $derived.by(() => {
		const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
		return INDICATORS.filter(
			(d) =>
				(category === 'all' || d.category === category) &&
				terms.every((t) =>
					`${d.name} ${d.short} ${d.id} ${d.description} ${d.outputs.map((o) => o.label).join(' ')}`
						.toLowerCase()
						.includes(t)
				)
		);
	});
	const groups = $derived(groupBy(results, (d) => d.category));
</script>

<div class="grid gap-[15px]" data-testid="indicator-reference">
	<div class="flex flex-wrap items-center gap-3">
		<div class="relative w-full max-w-sm">
			<Search
				class="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-muted"
				aria-hidden="true"
			/>
			<Input
				bind:value={query}
				type="search"
				placeholder="Search {INDICATORS.length} indicators"
				aria-label="Search indicators"
				class="pl-10"
			/>
		</div>
		<ToggleGroup.Root
			type="single"
			size="sm"
			value={category}
			onValueChange={(v) => (category = (v || 'all') as typeof category)}
			aria-label="Filter by category"
			class="flex-wrap"
		>
			<ToggleGroup.Item value="all">All</ToggleGroup.Item>
			{#each INDICATOR_CATEGORIES as c (c)}
				<ToggleGroup.Item value={c}>{c}</ToggleGroup.Item>
			{/each}
		</ToggleGroup.Root>
	</div>

	<p
		class="type-caption text-ink-muted tabular-nums"
		aria-live="polite"
		data-testid="indicator-count"
	>
		Showing {results.length} of {INDICATORS.length}
	</p>

	{#each groups as [name, items] (name)}
		<div class="grid gap-2">
			<h3 class="type-headline">{name}</h3>
			<ul class="grid grid-cols-[minmax(0,1fr)] gap-2 md:grid-cols-2">
				{#each items as d (d.id)}
					<!-- content-visibility skips layout and paint for cards that are scrolled far off screen. -->
					<li
						class="grid content-start gap-2 rounded-lg bg-surface-1 p-[15px] [contain-intrinsic-size:auto_120px] [content-visibility:auto]"
						data-testid="indicator-item"
					>
						<div class="flex flex-wrap items-center gap-2">
							<h4 class="type-body-sm">{d.name}</h4>
							<Badge variant="secondary">{d.short}</Badge>
							<Badge variant="secondary"
								>{d.pane === 'price' ? 'Overlay on price' : 'Own pane'}</Badge
							>
						</div>
						<p class="type-caption text-pretty text-ink-muted">{d.description}</p>
						{#if d.params.length}
							<p class="type-micro text-ink-muted tabular-nums">
								{#each d.params as p, i (p.key)}{i ? ' · ' : ''}{p.label}
									{p.default}
									<span class="opacity-80">({p.min} to {p.max})</span>{/each}
							</p>
						{/if}
						{#if d.outputs.length > 1 || d.guides?.length}
							<p class="type-micro text-ink-muted">
								{#if d.outputs.length > 1}Outputs: {d.outputs.map((o) => o.label).join(', ')}.{/if}
								{#if d.guides?.length}
									Reference levels {d.guides.join(', ')}.{/if}
							</p>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{:else}
		<p
			class="rounded-xl bg-surface-1 px-5 py-[30px] text-center type-body text-ink-muted"
			role="status"
		>
			No indicator matches “{query}”{category === 'all' ? '' : ` in ${category}`}.
		</p>
	{/each}
</div>
