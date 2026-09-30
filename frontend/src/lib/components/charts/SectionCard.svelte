<script lang="ts">
	import type { Snippet } from 'svelte';
	import Info from '@lucide/svelte/icons/info';

	interface Props {
		id: string;
		title: string;
		description?: string;
		/** Why the backend could not compute this section; when set the body is replaced by the reason. */
		unavailable?: string | null;
		/** Controls shown at the right of the header (toggle groups, selects). */
		actions?: Snippet;
		children: Snippet;
		class?: string;
	}

	let {
		id,
		title,
		description,
		unavailable = null,
		actions,
		children,
		class: className = ''
	}: Props = $props();
</script>

<section
	{id}
	aria-labelledby="{id}-title"
	class="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-5 rounded-xl bg-surface-1 p-5 {className}"
>
	<header class="flex flex-wrap items-start gap-x-[15px] gap-y-3">
		<div class="grid min-w-0 flex-1 gap-1">
			<h2 id="{id}-title" class="type-headline">{title}</h2>
			{#if description}<p class="max-w-[62ch] type-caption text-pretty text-ink-muted">
					{description}
				</p>{/if}
		</div>
		{#if actions && !unavailable}<div class="flex flex-wrap items-center gap-2">
				{@render actions()}
			</div>{/if}
	</header>
	{#if unavailable}
		<p
			class="flex items-start gap-3 rounded-lg bg-canvas p-[15px] type-body text-ink-muted"
			role="status"
			data-testid="unavailable"
		>
			<Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<span class="text-pretty">Not available for this dataset: {unavailable}</span>
		</p>
	{:else}
		{@render children()}
	{/if}
</section>
