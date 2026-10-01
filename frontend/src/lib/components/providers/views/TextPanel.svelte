<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TextView } from '$lib/api/providers';

	let { view }: { view: TextView } = $props();

	const STEP = 10;
	let count = $state(STEP);
	const blocks = $derived(view.blocks.slice(0, count));
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	<div class="grid gap-4">
		{#each blocks as block, i (i)}
			<article class="grid gap-1.5 rounded-lg bg-canvas p-4" data-testid="text-block">
				{#if block.heading || block.badge}
					<header class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
						{#if block.heading}<h3 class="type-subhead">{block.heading}</h3>{/if}
						{#if block.subheading}<span class="type-caption text-ink-muted">{block.subheading}</span
							>{/if}
						{#if block.badge}<Badge variant="secondary" class="ml-auto">{block.badge}</Badge>{/if}
					</header>
				{/if}
				<p class="max-w-[75ch] type-body-sm text-pretty whitespace-pre-line text-ink-muted">
					{block.body}
				</p>
			</article>
		{/each}
	</div>
	<div class="flex flex-wrap items-center justify-between gap-3 type-caption text-ink-muted">
		<span>Showing {blocks.length} of {view.blocks.length}</span>
		{#if count < view.blocks.length}
			<Button variant="translucent" size="sm" onclick={() => (count += STEP)}>Show more</Button>
		{/if}
	</div>
	{#if view.truncated}
		<p class="type-caption text-ink-muted" data-testid="text-truncated">
			The provider returned {view.total_blocks} blocks; the first {view.blocks.length} are included.
		</p>
	{/if}
</SectionCard>
