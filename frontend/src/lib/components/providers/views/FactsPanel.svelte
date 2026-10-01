<script lang="ts">
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { FactsView } from '$lib/api/providers';
	import { formatFact } from '$lib/providers/format';
	import ExternalLink from '../ExternalLink.svelte';

	let { view }: { view: FactsView } = $props();

	const LONG = 48;
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	{#each view.groups as group, g (g)}
		<div class="grid gap-3">
			{#if group.title}<h3 class="type-subhead text-ink-muted">{group.title}</h3>{/if}
			<dl class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
				{#each group.items as fact (fact.key)}
					{@const text = formatFact(fact)}
					<div
						class="grid content-start gap-1 rounded-lg bg-canvas p-3 {text.length > LONG
							? 'col-span-full'
							: ''}"
						data-testid="fact"
					>
						<dt class="type-caption text-ink-muted">{fact.label}</dt>
						<dd
							class="min-w-0 type-body text-pretty break-words tabular-nums {fact.tone ===
							'positive'
								? 'text-success-ink'
								: fact.tone === 'negative'
									? 'text-coral-ink'
									: 'text-ink'}"
						>
							{#if fact.format === 'url' && typeof fact.value === 'string'}
								<ExternalLink href={fact.value}>{fact.value}</ExternalLink>
							{:else}
								{fact.tone === 'positive' && typeof fact.value === 'number' && fact.value > 0
									? '+'
									: ''}{text}
							{/if}
						</dd>
						{#if fact.hint}<p class="type-caption text-ink-muted">{fact.hint}</p>{/if}
					</div>
				{/each}
			</dl>
		</div>
	{/each}
</SectionCard>
