<script lang="ts">
	import AreaChart from '$lib/components/charts/AreaChart.svelte';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import CandleChart from '$lib/components/app/CandleChart.svelte';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { SeriesView } from '$lib/api/providers';
	import { toCandles, toLines, populated, LINE_COLORS } from '$lib/providers/series';
	import { formatValue } from '$lib/format';

	let { view }: { view: SeriesView } = $props();

	const candles = $derived(toCandles(view));
	let mode = $state<'candles' | 'lines'>('candles');
	const showCandles = $derived(candles !== null && mode === 'candles');

	const keys = $derived(populated(view));
	let hidden = $state<string[]>([]);
	const shown = $derived(keys.filter((k) => !hidden.includes(k)));
	const lines = $derived(toLines(view, shown));
	const swatch = (key: string) => {
		const entry = toLines(view).find((l) => l.key === key);
		return entry?.color ?? LINE_COLORS[0];
	};

	function toggle(key: string) {
		if (hidden.includes(key)) hidden = hidden.filter((k) => k !== key);
		else if (shown.length > 1) hidden = [...hidden, key];
	}

	const label = $derived(`${view.title}${view.subtitle ? `, ${view.subtitle}` : ''}`);
	const axis = (v: number) => formatValue(v, 'compact');
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	{#snippet actions()}
		{#if candles}
			<ToggleGroup.Root
				type="single"
				size="sm"
				value={mode}
				onValueChange={(v) => v && (mode = v as typeof mode)}
				aria-label="Chart style"
			>
				<ToggleGroup.Item value="candles">Candles</ToggleGroup.Item>
				<ToggleGroup.Item value="lines">Lines</ToggleGroup.Item>
			</ToggleGroup.Root>
		{/if}
	{/snippet}

	{#if showCandles && candles}
		<CandleChart
			columns={candles.columns}
			overlays={[]}
			panes={[]}
			mask={null}
			showVolume={candles.hasVolume}
			intraday={view.intraday}
			label="Candlestick chart: {label}"
		/>
		{#if candles.dropped > 0}
			<p class="type-caption text-ink-muted" data-testid="dropped-bars">
				{candles.dropped} bar{candles.dropped === 1 ? '' : 's'} with a missing price {candles.dropped ===
				1
					? 'is'
					: 'are'} not drawn.
			</p>
		{/if}
	{:else}
		{#if keys.length > 1}
			<div class="flex flex-wrap gap-2" role="group" aria-label="Series shown">
				{#each keys as key (key)}
					{@const on = shown.includes(key)}
					<button
						type="button"
						aria-pressed={on}
						onclick={() => toggle(key)}
						class="inline-flex items-center gap-2 rounded-pill bg-surface-2 px-3 py-1.5 type-caption text-ink transition-opacity duration-150 ease-out aria-[pressed=false]:opacity-50 pointer-coarse:min-h-11"
					>
						<span class="size-2.5 rounded-full" style:background={swatch(key)} aria-hidden="true"
						></span>
						{view.series.find((s) => s.key === key)?.label}
					</button>
				{/each}
			</div>
		{/if}
		<AreaChart time={view.time} series={lines} leftFormat={axis} {label} />
	{/if}

	{#if view.time_note}
		<p class="type-caption text-ink-muted" data-testid="time-note">{view.time_note}</p>
	{/if}
	{#if view.truncated}
		<p class="type-caption text-ink-muted" data-testid="series-truncated">
			Showing the most recent {view.time.length.toLocaleString('en-US')} of {view.total_points.toLocaleString(
				'en-US'
			)} points.
		</p>
	{/if}
</SectionCard>
