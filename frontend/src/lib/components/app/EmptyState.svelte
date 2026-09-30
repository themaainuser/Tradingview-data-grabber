<script lang="ts">
	import type { Component, Snippet } from 'svelte';
	import SpotlightCard from './SpotlightCard.svelte';

	interface Props {
		title: string;
		description?: string;
		icon?: Component;
		/** Renders the state as a gradient spotlight card instead of a charcoal card. */
		tone?: 'violet' | 'magenta' | 'orange';
		/** Optional call to action. */
		children?: Snippet;
	}

	let { title, description, icon: Icon, tone, children }: Props = $props();
</script>

{#snippet body()}
	<div class="flex flex-col items-start gap-[15px]" role="status">
		{#if Icon}
			<div
				class="flex size-10 items-center justify-center rounded-full {tone
					? 'bg-black/30 text-current'
					: 'bg-surface-2 text-ink-muted'}"
			>
				<Icon class="size-5" aria-hidden="true" />
			</div>
		{/if}
		<h3 class={tone ? 'max-w-xl type-display-md' : 'type-headline'}>{title}</h3>
		{#if description}
			<p class="max-w-xl text-pretty {tone ? 'type-body-lg' : 'type-body text-ink-muted'}">
				{description}
			</p>
		{/if}
		{#if children}
			<div class="mt-1 flex flex-wrap items-center gap-2">{@render children()}</div>
		{/if}
	</div>
{/snippet}

{#if tone}
	<SpotlightCard {tone}>{@render body()}</SpotlightCard>
{:else}
	<div class="rounded-xl bg-surface-1 p-[30px]">{@render body()}</div>
{/if}
