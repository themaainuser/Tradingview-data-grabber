<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Attachment } from 'svelte/attachments';

	interface Props {
		/** Total number of rows. Only the visible window (plus overscan) is ever rendered. */
		count: number;
		/** Fixed row height in px; fixed heights make the window a pure function of scrollTop. */
		itemHeight?: number;
		overscan?: number;
		/** Accessible name of the table. */
		label: string;
		/** Optional stable key per row index so rows keep identity across sorting/filtering. */
		key?: (index: number) => string | number;
		/** Minimum content width in px; the list scrolls horizontally below it. */
		minWidth?: number;
		class?: string;
		header?: Snippet;
		row: Snippet<[index: number]>;
		empty?: Snippet;
	}

	let {
		count,
		itemHeight = 32,
		overscan = 8,
		label,
		key,
		minWidth,
		class: className = '',
		header,
		row,
		empty
	}: Props = $props();

	let scrollTop = $state(0);
	let viewport = $state(480);

	// Window of row indexes to render. Derived, so scrolling only re-renders rows entering/leaving.
	const first = $derived(Math.max(0, Math.floor(scrollTop / itemHeight) - overscan));
	const last = $derived(Math.min(count, Math.ceil((scrollTop + viewport) / itemHeight) + overscan));
	const visible = $derived(Array.from({ length: Math.max(0, last - first) }, (_, i) => first + i));

	// Keeps `viewport` in sync with the element height (resizes, layout changes). The list only
	// virtualises when its own height is bounded (e.g. `max-h-96`); an unbounded parent would
	// make it as tall as all rows, so the measurement is capped to keep the DOM small regardless.
	const measure: Attachment<HTMLDivElement> = (element) => {
		const read = () => {
			viewport = Math.min(element.clientHeight, 3 * window.innerHeight);
		};
		read();
		const observer = new ResizeObserver(read);
		observer.observe(element);
		return () => observer.disconnect();
	};
</script>

<div
	class="relative overflow-auto {className}"
	role="table"
	aria-label={label}
	aria-rowcount={count + 1}
	onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)}
	{@attach measure}
>
	<div style:min-width={minWidth ? `${minWidth}px` : undefined}>
		{#if header}
			<div class="sticky top-0 z-10 border-b border-hairline bg-inherit" role="rowgroup">
				<div role="row" aria-rowindex={1}>{@render header()}</div>
			</div>
		{/if}
		{#if count === 0}
			{@render empty?.()}
		{:else}
			<div class="relative" role="rowgroup" style:height="{count * itemHeight}px">
				{#each visible as index (key ? key(index) : index)}
					<div
						class="absolute inset-x-0 border-b border-hairline-soft"
						role="row"
						aria-rowindex={index + 2}
						style:height="{itemHeight}px"
						style:transform="translateY({index * itemHeight}px)"
					>
						{@render row(index)}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
