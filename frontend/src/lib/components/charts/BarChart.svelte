<script lang="ts">
	import {
		assignRows,
		clamp,
		extent,
		formatNumber,
		linePath,
		mergeExtents,
		stepIndex
	} from '$lib/charts/chart-math';
	import { formatAxis, niceTicks } from '$lib/charts/scale';
	import { MISSING } from '$lib/format';
	import ChartTooltip from './ChartTooltip.svelte';
	import { measure } from './measure';
	import type { BarMarker } from './types';

	interface Props {
		labels: readonly string[];
		values: readonly (number | null)[];
		/** Thin line through the bar centres (for example a fitted normal curve), same scale as the bars. */
		overlay?: readonly (number | null)[];
		overlayLabel?: string;
		/** sign: non-negative green, negative coral. solid: muted, emphasised on hover. */
		colorBy?: 'sign' | 'solid';
		format?: (value: number) => string;
		/** Default: drawn when any value is negative. */
		zeroLine?: boolean;
		/** Show every n-th x label; default picks from the available width. */
		labelEvery?: number;
		height?: number;
		/** Dashed vertical lines at a bar index with a caption, such as "VaR 95%". */
		markers?: readonly BarMarker[];
		/** Accessible name of the chart. */
		label: string;
		class?: string;
	}

	let {
		labels,
		values,
		overlay,
		overlayLabel = 'Overlay',
		colorBy = 'solid',
		format,
		zeroLine,
		labelEvery,
		height = 220,
		markers = [],
		label,
		class: className = ''
	}: Props = $props();

	const BOTTOM = 26;
	const RIGHT = 10;
	const ROW = 14;

	let width = $state(0);
	let cursor = $state<number | null>(null);
	let byKeyboard = $state(false);
	let svgEl = $state<SVGSVGElement>();
	const size = measure((w) => (width = w));

	const n = $derived(values.length);
	const fmt = $derived(format ?? formatNumber);
	const isNumber = (v: number | null | undefined): v is number =>
		typeof v === 'number' && Number.isFinite(v);

	// Bars grow from zero, so the zero side of the domain is never padded.
	const dom = $derived.by((): [number, number] => {
		const e = mergeExtents([extent(values), extent(overlay ?? []), [0, 0]]) ?? [0, 1];
		const span = e[1] - e[0] || 1;
		const lo = e[0] < 0 ? e[0] - span * 0.06 : 0;
		const hi = e[1] > 0 ? e[1] + span * 0.06 : 0;
		return hi > lo ? [lo, hi] : [0, 1];
	});
	const ticks = $derived.by(() => {
		const list = niceTicks(dom[0], dom[1], Math.max(2, Math.floor((height - 40) / 40)));
		const step = list.length > 1 ? list[1] - list[0] : 1;
		return list.map((value) => ({
			value,
			text: format ? format(value) : formatAxis(value, step)
		}));
	});
	const marginLeft = $derived(
		Math.max(32, ticks.reduce((m, t) => Math.max(m, t.text.length), 0) * 6.6 + 14)
	);
	const plotW = $derived(Math.max(10, width - marginLeft - RIGHT));
	const step = $derived(plotW / Math.max(1, n));
	const centre = (i: number) => (i + 0.5) * step;

	// Captions that would collide stack into extra rows above the plot.
	const markerLayout = $derived.by(() => {
		const placed = markers
			.filter((m) => m.index >= 0 && m.index < n)
			.map((m) => {
				const w = m.label.length * 6.3 + 4;
				const x = centre(m.index);
				const right = x + 4 + w <= plotW;
				return { m, x, right, start: right ? x + 4 : x - 4 - w, end: right ? x + 4 + w : x - 4 };
			});
		const rows = assignRows(placed, 6);
		return placed.map((p, i) => ({ ...p, row: rows[i] }));
	});
	const top = $derived(
		10 + (markerLayout.length ? (Math.max(...markerLayout.map((p) => p.row)) + 1) * ROW : 0)
	);
	const plotH = $derived(Math.max(10, height - top - BOTTOM));
	const yOf = $derived((v: number) =>
		clamp((1 - (v - dom[0]) / (dom[1] - dom[0])) * plotH, -1e4, 1e4)
	);
	const y0 = $derived(yOf(0));
	const showZero = $derived(zeroLine ?? values.some((v) => isNumber(v) && v < 0));

	const gapRatio = $derived(step > 8 ? 0.2 : step > 3 ? 0.1 : 0);
	const barW = $derived(Math.max(1, step * (1 - gapRatio)));
	const bars = $derived(
		values.flatMap((v, i) => {
			if (!isNumber(v)) return [];
			const y = yOf(v);
			return [{ i, v, x: i * step + (step - barW) / 2, y: Math.min(y, y0), h: Math.abs(y - y0) }];
		})
	);
	const overlayD = $derived(
		overlay
			? linePath(
					Array.from({ length: n }, (_, i) => i),
					overlay,
					centre,
					yOf
				)
			: ''
	);

	const every = $derived(
		Math.max(
			1,
			Math.floor(
				labelEvery ??
					Math.ceil(
						(labels.reduce((m, l) => Math.max(m, l.length), 0) * 6.4 + 10) / Math.max(1, step)
					)
			)
		)
	);

	const colorOf = (v: number) =>
		colorBy === 'sign' ? (v >= 0 ? 'var(--chart-up)' : 'var(--chart-down)') : 'var(--ink)';
	const fillOf = (i: number, v: number) =>
		colorBy === 'sign' ? colorOf(v) : i === cursor ? 'var(--ink)' : 'var(--ink-muted)';
	const opacityOf = (i: number) =>
		colorBy === 'sign' ? (cursor === null ? 0.9 : i === cursor ? 1 : 0.5) : 1;

	const tooltip = $derived.by(() => {
		if (cursor === null || cursor >= n) return null;
		const v = values[cursor];
		const o = overlay?.[cursor];
		return {
			x: marginLeft + centre(cursor),
			y: top + (isNumber(v) ? Math.min(yOf(v), y0) : plotH / 2),
			title: labels[cursor] ?? String(cursor),
			rows: [
				{
					label: 'Value',
					color: isNumber(v) ? colorOf(v) : undefined,
					value: isNumber(v) ? fmt(v) : MISSING
				},
				...(overlay
					? [
							{
								label: overlayLabel,
								color: 'var(--ink)',
								swatch: 'line' as const,
								value: isNumber(o) ? fmt(o) : MISSING
							}
						]
					: [])
			]
		};
	});
	const readout = $derived(
		byKeyboard && tooltip
			? `${tooltip.title}: ${tooltip.rows.map((r) => `${r.label} ${r.value}`).join(', ')}`
			: ''
	);

	function track(e: PointerEvent) {
		if (!svgEl || n === 0) return;
		const rect = svgEl.getBoundingClientRect();
		const px = e.clientX - rect.left - marginLeft;
		const py = e.clientY - rect.top;
		if (px < 0 || px > plotW || py < 0 || py > height) {
			cursor = null;
			return;
		}
		byKeyboard = false;
		cursor = clamp(Math.floor(px / step), 0, n - 1);
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.altKey || e.ctrlKey || e.metaKey) return;
		if (e.key === 'Escape') {
			if (cursor !== null) e.preventDefault();
			cursor = null;
			return;
		}
		const next = stepIndex(e.key, cursor, n, { axis: 'x' });
		if (next === null) return;
		e.preventDefault();
		byKeyboard = true;
		cursor = next;
	}

	function onfocus(e: FocusEvent & { currentTarget: HTMLElement }) {
		if (cursor === null && n > 0 && e.currentTarget.matches(':focus-visible')) {
			byKeyboard = true;
			cursor = 0;
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
				<g transform="translate({marginLeft} 0)">
					{#each markerLayout as p, k (k)}
						<text
							data-marker={p.m.index}
							class="fill-ink text-[11px]"
							x={p.right ? p.x + 4 : p.x - 4}
							y={10 + p.row * ROW}
							text-anchor={p.right ? 'start' : 'end'}
							dominant-baseline="central">{p.m.label}</text
						>
					{/each}
				</g>
				<g transform="translate({marginLeft} {top})">
					{#each ticks as tick (tick.value)}
						<line
							class="stroke-hairline"
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

					{#each bars as b (b.i)}
						<rect
							data-index={b.i}
							class="transition-[fill,opacity] duration-100"
							x={b.x}
							y={b.y}
							width={barW}
							height={b.h}
							rx={Math.min(2, barW / 2)}
							opacity={opacityOf(b.i)}
							style:fill={fillOf(b.i, b.v)}
						/>
					{/each}

					{#if showZero}
						<line
							data-zero
							class="stroke-ink-muted"
							x1="0"
							x2={plotW}
							y1={y0}
							y2={y0}
							stroke-opacity="0.6"
							shape-rendering="crispEdges"
						/>
					{/if}

					{#each markerLayout as p, k (k)}
						{@const y1 = -top + 10 + p.row * ROW + 7}
						<!-- The dark under-stroke keeps the dashes readable where they cross bars. -->
						<line
							x1={p.x}
							x2={p.x}
							{y1}
							y2={plotH}
							stroke-width="3"
							stroke-dasharray="4 3"
							stroke-opacity="0.8"
							style:stroke="var(--chart-bg)"
						/>
						<line
							data-marker-line={p.m.index}
							class="stroke-ink"
							x1={p.x}
							x2={p.x}
							{y1}
							y2={plotH}
							stroke-dasharray="4 3"
							stroke-opacity="0.9"
						/>
					{/each}

					{#if overlayD}
						<path
							data-overlay
							d={overlayD}
							fill="none"
							stroke-width="1.5"
							stroke-linejoin="round"
							stroke-linecap="round"
							style:stroke="var(--ink)"
						/>
					{/if}

					{#each labels as text, i (i)}
						{#if i % every === 0}
							<text
								class="fill-ink-muted text-[11px] tabular-nums"
								x={centre(i)}
								y={plotH + 17}
								text-anchor="middle">{text}</text
							>
						{/if}
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
					<th scope="col">Bin</th>
					<th scope="col">Value</th>
					{#if overlay}<th scope="col">{overlayLabel}</th>{/if}
				</tr>
			</thead>
			<tbody>
				{#each values as v, i (i)}
					<tr>
						<th scope="row">{labels[i] ?? i}</th>
						<td>{isNumber(v) ? fmt(v) : MISSING}</td>
						{#if overlay}<td>{isNumber(overlay[i]) ? fmt(overlay[i]) : MISSING}</td>{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="sr-only" aria-live="polite" aria-atomic="true">{readout}</p>
</div>
