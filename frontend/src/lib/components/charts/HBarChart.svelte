<script lang="ts">
	import { binIndex, clamp, formatNumber, nudgeApart, stepIndex } from '$lib/charts/chart-math';
	import { formatAxis, niceTicks } from '$lib/charts/scale';
	import ChartTooltip from './ChartTooltip.svelte';
	import { measure } from './measure';
	import type { HBarMarker, HBarRange } from './types';

	interface Props {
		/** n + 1 ascending price edges; bin i spans edges[i] to edges[i + 1]. */
		edges: readonly number[];
		/** n volumes (>= 0), one per bin. */
		values: readonly number[];
		/** Horizontal lines across the plot with a caption on the right (POC, last price...). */
		markers?: readonly HBarMarker[];
		/** Value area: bars inside are drawn in ink, bars outside muted, with a subtle band behind. */
		range?: HBarRange;
		priceFormat?: (value: number) => string;
		valueFormat?: (value: number) => string;
		height?: number;
		/** Accessible name of the chart. */
		label: string;
		class?: string;
	}

	let {
		edges,
		values,
		markers = [],
		range,
		priceFormat,
		valueFormat,
		height = 360,
		label,
		class: className = ''
	}: Props = $props();

	const TOP = 8;
	const BOTTOM = 8;
	const LABEL_ROW = 14;

	let width = $state(0);
	let cursor = $state<number | null>(null);
	let byKeyboard = $state(false);
	let svgEl = $state<SVGSVGElement>();
	const size = measure((w) => (width = w));

	const n = $derived(Math.max(0, Math.min(values.length, edges.length - 1)));
	const price = $derived(priceFormat ?? formatNumber);
	const volume = $derived(valueFormat ?? formatNumber);
	const lowEdge = $derived(n ? edges[0] : 0);
	const highEdge = $derived(n ? edges[n] : 1);
	const plotH = $derived(Math.max(10, height - TOP - BOTTOM));
	const yOf = $derived((p: number) =>
		clamp((1 - (p - lowEdge) / (highEdge - lowEdge || 1)) * plotH, -1e4, 1e4)
	);
	const maxValue = $derived(values.slice(0, n).reduce((m, v) => (v > m ? v : m), 0));
	const total = $derived(values.slice(0, n).reduce((s, v) => s + (v > 0 ? v : 0), 0));
	const peak = $derived(values.slice(0, n).reduce((best, v, i, a) => (v > a[best] ? i : best), 0));

	const ticks = $derived.by(() => {
		const list = niceTicks(lowEdge, highEdge, Math.max(2, Math.floor(plotH / 36)));
		const step = list.length > 1 ? list[1] - list[0] : 1;
		return list.map((value) => ({
			value,
			text: priceFormat ? priceFormat(value) : formatAxis(value, step)
		}));
	});
	const marginLeft = $derived(
		Math.max(32, ticks.reduce((m, t) => Math.max(m, t.text.length), 0) * 6.6 + 14)
	);

	// Marker and range captions share a gutter on the right; they are nudged so none overlap.
	const visibleMarkers = $derived(
		markers.filter((m) => n > 0 && m.value >= lowEdge && m.value <= highEdge)
	);
	const captions = $derived.by(() => {
		const items = [
			...visibleMarkers.map((m) => ({ text: m.label, at: yOf(m.value), kind: 'marker' as const })),
			...(range?.label && n > 0
				? [{ text: range.label, at: yOf(range.high) + LABEL_ROW / 2, kind: 'range' as const }]
				: [])
		];
		const ys = nudgeApart(
			items.map((c) => c.at),
			LABEL_ROW,
			LABEL_ROW / 2 - 4,
			plotH - LABEL_ROW / 2 + 4
		);
		return items.map((c, i) => ({ ...c, y: ys[i] }));
	});
	const gutter = $derived(
		captions.length ? captions.reduce((m, c) => Math.max(m, c.text.length), 0) * 6.3 + 18 : 10
	);
	const plotW = $derived(Math.max(10, width - marginLeft - gutter));

	const bars = $derived(
		Array.from({ length: n }, (_, i) => {
			const top = yOf(edges[i + 1]);
			const full = yOf(edges[i]) - top;
			const gap = full > 4 ? 1 : 0;
			const mid = (edges[i] + edges[i + 1]) / 2;
			const inside = range ? mid >= range.low && mid <= range.high : true;
			return {
				i,
				y: top + gap / 2,
				h: Math.max(1, full - gap),
				w: maxValue > 0 ? (Math.max(0, values[i]) / maxValue) * plotW : 0,
				inside
			};
		})
	);
	const rangeBand = $derived(
		range && n > 0
			? (() => {
					const y1 = clamp(yOf(range.high), 0, plotH);
					const y2 = clamp(yOf(range.low), 0, plotH);
					return y2 > y1 ? { y: y1, h: y2 - y1 } : null;
				})()
			: null
	);

	const fillOf = (b: { i: number; inside: boolean }) =>
		b.i === cursor || (range && b.inside) ? 'var(--ink)' : 'var(--ink-muted)';
	const opacityOf = (b: { i: number; inside: boolean }) =>
		b.i === cursor ? 1 : range ? (b.inside ? 0.9 : 0.5) : 0.85;

	const share = (v: number) =>
		total > 0 ? `${((Math.max(0, v) / total) * 100).toFixed(1)}%` : '0.0%';
	const binText = (i: number) => `${price(edges[i])} \u2013 ${price(edges[i + 1])}`;
	const tooltip = $derived(
		cursor === null || cursor >= n
			? null
			: {
					x: marginLeft + bars[cursor].w,
					y: TOP + bars[cursor].y + bars[cursor].h / 2,
					title: binText(cursor),
					rows: [
						{ label: 'Volume', value: volume(values[cursor]) },
						{ label: 'Share', value: share(values[cursor]) }
					]
				}
	);
	const readout = $derived(
		byKeyboard && tooltip
			? `${tooltip.title}: ${tooltip.rows.map((r) => `${r.label} ${r.value}`).join(', ')}`
			: ''
	);

	function track(e: PointerEvent) {
		if (!svgEl || n === 0) return;
		const rect = svgEl.getBoundingClientRect();
		const px = e.clientX - rect.left - marginLeft;
		const py = e.clientY - rect.top - TOP;
		if (px < 0 || px > plotW + gutter || py < 0 || py > plotH) {
			cursor = null;
			return;
		}
		byKeyboard = false;
		cursor = binIndex(edges.slice(0, n + 1), lowEdge + (1 - py / plotH) * (highEdge - lowEdge));
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.altKey || e.ctrlKey || e.metaKey) return;
		if (e.key === 'Escape') {
			if (cursor !== null) e.preventDefault();
			cursor = null;
			return;
		}
		const next = stepIndex(e.key, cursor, n, { axis: 'y' });
		if (next === null) return;
		e.preventDefault();
		byKeyboard = true;
		cursor = next;
	}

	function onfocus(e: FocusEvent & { currentTarget: HTMLElement }) {
		if (cursor === null && n > 0 && e.currentTarget.matches(':focus-visible')) {
			byKeyboard = true;
			cursor = peak;
		}
	}

	function leave() {
		cursor = null;
		byKeyboard = false;
	}
</script>

<div class="relative min-w-0 {className}" {@attach size}>
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<div
		tabindex="0"
		role="group"
		aria-label={label}
		class="block touch-pan-y rounded-lg"
		onpointermove={track}
		onpointerdown={track}
		onpointerleave={(e) => e.pointerType !== 'touch' && leave()}
		{onkeydown}
		{onfocus}
		onblur={leave}
	>
		{#if width > 0}
			<svg
				bind:this={svgEl}
				{width}
				{height}
				class="block max-w-full"
				aria-hidden="true"
				focusable="false"
			>
				<g transform="translate({marginLeft} {TOP})">
					{#if rangeBand}
						<rect
							data-range
							x="0"
							y={rangeBand.y}
							width={plotW + gutter - 4}
							height={rangeBand.h}
							fill-opacity="0.06"
							style:fill="var(--ink)"
						/>
					{/if}
					{#each ticks as tick (tick.value)}
						<line
							class="stroke-hairline-soft"
							x1="0"
							x2={plotW}
							y1={yOf(tick.value)}
							y2={yOf(tick.value)}
							shape-rendering="crispEdges"
						/>
						<text
							class="fill-ink-muted text-[11px] tabular-nums"
							x="-8"
							y={yOf(tick.value)}
							text-anchor="end"
							dominant-baseline="central">{tick.text}</text
						>
					{/each}
					<line
						class="stroke-hairline"
						x1="0"
						x2="0"
						y1="0"
						y2={plotH}
						shape-rendering="crispEdges"
					/>

					{#each bars as b (b.i)}
						<rect
							data-index={b.i}
							class="transition-[fill,opacity] duration-100"
							x="0"
							y={b.y}
							width={b.w}
							height={b.h}
							rx={Math.min(2, b.h / 2)}
							opacity={opacityOf(b)}
							style:fill={fillOf(b)}
						/>
					{/each}

					{#each visibleMarkers as m, k (k)}
						<!-- The dark under-stroke keeps the dashes readable where they cross bars. -->
						<line
							x1="0"
							x2={plotW + 6}
							y1={yOf(m.value)}
							y2={yOf(m.value)}
							stroke-width="3"
							stroke-dasharray="4 3"
							stroke-opacity="0.8"
							style:stroke="var(--chart-bg)"
						/>
						<line
							data-marker-line={k}
							class="stroke-ink"
							x1="0"
							x2={plotW + 6}
							y1={yOf(m.value)}
							y2={yOf(m.value)}
							stroke-dasharray="4 3"
							stroke-opacity="0.9"
						/>
					{/each}
					{#each captions as c, k (k)}
						<text
							data-caption={c.kind}
							class="text-[11px] tabular-nums {c.kind === 'marker' ? 'fill-ink' : 'fill-ink-muted'}"
							x={plotW + 10}
							y={c.y}
							dominant-baseline="central">{c.text}</text
						>
					{/each}
				</g>
			</svg>
		{:else}
			<div style:height="{height}px"></div>
		{/if}
	</div>
	{#if tooltip}
		<ChartTooltip
			x={tooltip.x}
			y={tooltip.y}
			{width}
			{height}
			title={tooltip.title}
			rows={tooltip.rows}
		/>
	{/if}
	<!-- Tables ignore sr-only's 1px width and clip, so the wrapper div does the hiding. -->
	<div class="sr-only">
		<table>
			<caption>{label}</caption>
			<thead>
				<tr>
					<th scope="col">Price range</th>
					<th scope="col">Volume</th>
					<th scope="col">Share</th>
				</tr>
			</thead>
			<tbody>
				{#each values.slice(0, n) as v, i (i)}
					<tr>
						<th scope="row">{binText(i)}</th>
						<td>{volume(v)}</td>
						<td>{share(v)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="sr-only" aria-live="polite" aria-atomic="true">{readout}</p>
</div>
