<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { FeedView } from '$lib/api/providers';
	import { formatTimestamp, sentimentTone, sentimentWord } from '$lib/providers/format';
	import ExternalLink from '../ExternalLink.svelte';

	let { view }: { view: FeedView } = $props();

	const STEP = 15;
	let count = $state(STEP);
	const items = $derived(view.items.slice(0, count));

	const tone = (t: 'positive' | 'negative' | null) =>
		t === 'positive' ? 'text-success-ink' : t === 'negative' ? 'text-coral-ink' : 'text-ink-muted';
	const signed = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`;
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	<ul class="grid gap-3">
		{#each items as item, i (i)}
			<li class="grid gap-2 rounded-lg bg-canvas p-4" data-testid="feed-item">
				<div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
					<h3 class="min-w-0 flex-1 type-body text-pretty">
						<ExternalLink href={item.url} class="text-ink">{item.title}</ExternalLink>
					</h3>
					{#if item.sentiment}
						<span
							class="type-caption whitespace-nowrap {tone(sentimentTone(item.sentiment.score))}"
						>
							{sentimentWord(item.sentiment.score, item.sentiment.label)}{item.sentiment.score !==
							null
								? ` (${signed(item.sentiment.score)})`
								: ''}
						</span>
					{/if}
				</div>
				<p class="type-caption text-ink-muted">
					{[item.source, item.published !== null ? formatTimestamp(item.published) : null]
						.filter(Boolean)
						.join(' · ')}
				</p>
				{#if item.summary}<p class="line-clamp-3 type-body-sm text-pretty text-ink-muted">
						{item.summary}
					</p>{/if}
				{#if item.tags.length || item.tickers.length}
					<div class="flex flex-wrap gap-1.5">
						{#each item.tags as tag (tag)}<Badge variant="secondary">{tag}</Badge>{/each}
						{#each item.tickers as ticker (ticker.symbol)}
							<Badge variant="default" class="gap-1.5">
								{ticker.symbol}
								{#if ticker.score !== null}
									<span class={tone(sentimentTone(ticker.score))}>{signed(ticker.score)}</span>
								{/if}
							</Badge>
						{/each}
					</div>
				{/if}
			</li>
		{/each}
	</ul>
	<div class="flex flex-wrap items-center justify-between gap-3 type-caption text-ink-muted">
		<span>Showing {items.length} of {view.items.length}</span>
		{#if count < view.items.length}
			<Button variant="translucent" size="sm" onclick={() => (count += STEP)}>Show more</Button>
		{/if}
	</div>
	{#if view.truncated}
		<p class="type-caption text-ink-muted" data-testid="feed-truncated">
			The provider returned {view.total_items} articles; the first {view.items.length} are included.
		</p>
	{/if}
</SectionCard>
