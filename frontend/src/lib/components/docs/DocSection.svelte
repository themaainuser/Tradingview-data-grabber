<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		/** Anchor id; must match an entry in the contents list. */
		id: string;
		title: string;
		/** One-line lead shown under the heading. */
		lead?: string;
		/** Prose, kept to a readable line length. */
		children: Snippet;
		/** Reference tables and lists that need the full column width. */
		wide?: Snippet;
	}

	let { id, title, lead, children, wide }: Props = $props();
</script>

<!-- scroll-mt clears the sticky 56px header (and the mobile contents bar) when jumping to an anchor. -->
<section
	{id}
	aria-labelledby="{id}-title"
	class="grid scroll-mt-[124px] grid-cols-[minmax(0,1fr)] gap-5 xl:scroll-mt-[84px]"
>
	<header class="grid gap-2">
		<h2 id="{id}-title" class="type-display-md">
			<a href="#{id}" class="group/anchor inline-flex items-baseline gap-2 text-ink">
				{title}
				<span
					class="type-body text-ink-muted opacity-0 transition-opacity duration-150 ease-out group-hover/anchor:opacity-100 group-focus-visible/anchor:opacity-100"
					aria-hidden="true">#</span
				>
			</a>
		</h2>
		{#if lead}
			<p class="max-w-[60ch] type-body-lg text-pretty text-ink-muted">{lead}</p>
		{/if}
	</header>
	<div
		class="grid max-w-[760px] grid-cols-[minmax(0,1fr)] gap-4 type-body text-pretty [&_:not(pre)>code]:rounded-xs [&_:not(pre)>code]:bg-surface-2 [&_:not(pre)>code]:px-[5px] [&_:not(pre)>code]:py-[2px] [&_:not(pre)>code]:font-mono [&_:not(pre)>code]:text-[0.92em] [&_h3]:mt-3 [&_h3]:type-headline [&_li]:text-ink-muted [&_ul]:grid [&_ul]:list-disc [&_ul]:gap-2 [&_ul]:pl-5"
	>
		{@render children()}
	</div>
	{#if wide}
		<div class="grid min-w-0 gap-5">{@render wide()}</div>
	{/if}
</section>
