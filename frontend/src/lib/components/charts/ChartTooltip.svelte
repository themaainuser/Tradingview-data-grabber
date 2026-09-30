<script lang="ts">
	import type { TooltipRow } from './types';

	interface Props {
		/** Anchor point in the chart container's coordinates. */
		x: number;
		y: number;
		/** Container size, so the tooltip flips to the other side and stays inside. */
		width: number;
		height: number;
		title: string;
		rows: readonly TooltipRow[];
		/** Distance from the anchor to the tooltip edge. */
		gap?: number;
		/** Hang from `y` instead of centring on it. */
		hang?: boolean;
	}

	let { x, y, width, height, title, rows, gap = 12, hang = false }: Props = $props();

	let w = $state(0);
	let h = $state(0);

	const left = $derived(x + gap + w > width ? Math.max(0, x - gap - w) : x + gap);
	const top = $derived(Math.min(Math.max(0, hang ? y : y - h / 2), Math.max(0, height - h)));
</script>

<!-- Decorative duplicate of the aria-live readout, so screen readers skip it. -->
<div
	data-slot="chart-tooltip"
	aria-hidden="true"
	class="pointer-events-none absolute z-10 rounded-lg bg-surface-2 px-3 py-2 type-caption whitespace-nowrap text-ink tabular-nums shadow-float"
	style:left="{left}px"
	style:top="{top}px"
	style:visibility={w > 0 ? 'visible' : 'hidden'}
	bind:offsetWidth={w}
	bind:offsetHeight={h}
>
	<div class="text-ink-muted">{title}</div>
	{#each rows as row, i (i)}
		<div class="mt-1 flex items-center gap-2">
			{#if row.color}
				<span
					class="inline-block shrink-0 {row.swatch === 'line'
						? 'h-0.5 w-3'
						: 'size-2 rounded-full'}"
					style:background={row.color}
				></span>
			{/if}
			<span class="text-ink-muted">{row.label}</span>
			<span class="ml-auto pl-3 text-ink">{row.value}</span>
		</div>
	{/each}
</div>
