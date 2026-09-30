<script lang="ts">
	import type { Attachment } from 'svelte/attachments';
	import { CandleChartController } from '$lib/charts/candle-controller';
	import type { ChartPane, ChartSeries } from '$lib/charts/types';
	import { formatTime } from '$lib/charts/scale';
	import { formatValue } from '$lib/format';
	import type { OhlcvColumns } from '$lib/indicators/types';

	interface Props {
		columns: OhlcvColumns;
		overlays: readonly ChartSeries[];
		panes: readonly ChartPane[];
		/** Bars passing the active filter (highlighted on the chart), or null when no filter is active. */
		mask: Uint8Array | null;
		showVolume: boolean;
		label: string;
		/** Ask the chart to centre on a bar. A new `nonce` re-triggers the same index. */
		focus?: { index: number; nonce: number } | null;
		intraday?: boolean;
	}

	let {
		columns,
		overlays,
		panes,
		mask,
		showVolume,
		label,
		focus = null,
		intraday = true
	}: Props = $props();

	let hover = $state<number | null>(null);

	// The controller is a plain object owned by the attachment. Reactive props are pushed into it
	// from nested effects, so the attachment itself never re-runs (which would rebuild the canvas).
	const chart: Attachment<HTMLCanvasElement> = (canvas) => {
		const controller = new CandleChartController(canvas, { onHover: (index) => (hover = index) });
		$effect(() => {
			controller.set({ columns, overlays, panes, mask, showVolume });
		});
		$effect(() => {
			if (focus) controller.focus(focus.index);
		});
		return () => controller.destroy();
	};

	const index = $derived(hover ?? columns.close.length - 1);
	const up = $derived(columns.close[index] >= columns.open[index]);
	const height = $derived(320 + (showVolume ? 70 : 0) + panes.length * 150);

	const readouts = $derived([
		...overlays.map((s) => ({
			key: s.key,
			label: s.label,
			color: s.color,
			value: s.values[index]
		})),
		...panes.flatMap((p) =>
			p.series.map((s) => ({ key: s.key, label: s.label, color: s.color, value: s.values[index] }))
		)
	]);
</script>

<figure class="grid gap-2">
	<figcaption
		class="flex flex-wrap items-baseline gap-x-4 gap-y-1 type-caption tabular-nums"
		aria-live="off"
	>
		<span class="text-ink-muted">{formatTime(columns.time[index], intraday)} UTC</span>
		{#each [['O', columns.open], ['H', columns.high], ['L', columns.low], ['C', columns.close]] as const as [name, values] (name)}
			<span>
				<span class="text-ink-muted">{name}</span>
				<span class={up ? 'text-positive' : 'text-negative'}
					>{formatValue(values[index], 'price')}</span
				>
			</span>
		{/each}
		<span
			><span class="text-ink-muted">V</span>
			{formatValue(columns.volume[index], 'compact')}</span
		>
		{#each readouts as item (item.key)}
			<span class="inline-flex items-center gap-1">
				<span
					class="inline-block size-2 rounded-full"
					style:background="var({item.color})"
					aria-hidden="true"
				></span>
				<span class="text-ink-muted">{item.label}</span>
				{formatValue(item.value, 'number')}
			</span>
		{/each}
	</figcaption>
	<canvas
		{@attach chart}
		class="w-full touch-none rounded-lg outline-none"
		style:height="{height}px"
		tabindex="0"
		aria-label="{label}. Drag to pan, scroll to zoom, double-click to reset. Arrow keys pan, plus and minus zoom."
	></canvas>
	<p class="type-caption text-ink-muted">
		Drag to pan · scroll to zoom · double-click to reset · arrow keys and +/− when focused
	</p>
</figure>
