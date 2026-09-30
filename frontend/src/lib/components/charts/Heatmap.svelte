<script lang="ts">
	import {
		clamp,
		contrastInk,
		extent,
		formatNumber,
		heatColor,
		normalize,
		type HeatScale
	} from '$lib/charts/chart-math';
	import { MISSING } from '$lib/format';
	import { renderedTheme } from '$lib/state/theme.svelte';
	import ChartTooltip from './ChartTooltip.svelte';
	import { measure } from './measure';
	import type { HeatmapLegend } from './types';

	interface Props {
		rows: readonly string[];
		cols: readonly string[];
		/** rows x cols; null draws an empty cell. */
		values: readonly (readonly (number | null)[])[];
		scale?: HeatScale;
		/** Default: data extent; a diverging scale is symmetric about 0. */
		domain?: [number, number];
		format?: (value: number) => string;
		/** Print each value in its cell while cells are big enough to hold it. */
		showValues?: boolean;
		/** Show every n-th column label; default picks from the cell width. */
		colLabelEvery?: number;
		cellHeight?: number;
		/** Gradient bar under the grid with a caption at each end. */
		legend?: HeatmapLegend;
		/** Keep cells square (correlation matrices); they are capped at 64px. */
		square?: boolean;
		/** Accessible name of the grid. */
		label: string;
		class?: string;
	}

	let {
		rows,
		cols,
		values,
		scale = 'sequential',
		domain,
		format,
		showValues = false,
		colLabelEvery,
		cellHeight = 28,
		legend,
		square = false,
		label,
		class: className = ''
	}: Props = $props();

	const GAP = 2;
	const HEADER = 26;
	const MAX_SQUARE = 64;

	type Pos = { r: number; c: number };
	let width = $state(0);
	let pos = $state<Pos>({ r: 0, c: 0 });
	let hover = $state<Pos | null>(null);
	let focused = $state<Pos | null>(null);
	let gridEl = $state<HTMLElement>();
	const size = measure((w) => (width = w));

	const nr = $derived(rows.length);
	const nc = $derived(cols.length);
	const fmt = $derived(format ?? formatNumber);
	const longest = (list: readonly string[]) => list.reduce((m, s) => Math.max(m, s.length), 0);

	const gutter = $derived(
		Math.min(Math.round(width * 0.35), Math.max(24, longest(rows) * 6.4 + 16))
	);
	const cellW = $derived(
		Math.max(
			0,
			Math.min(
				square ? MAX_SQUARE : Infinity,
				(width - gutter - GAP - GAP * (nc - 1)) / Math.max(1, nc)
			)
		)
	);
	const cellH = $derived(square ? cellW : cellHeight);
	const gridW = $derived(nc * cellW + GAP * Math.max(0, nc - 1));
	const gridH = $derived(HEADER + GAP + nr * cellH + GAP * Math.max(0, nr - 1));
	const template = $derived(`${gutter}px repeat(${nc}, ${cellW}px)`);

	const dom = $derived.by((): [number, number] => {
		if (domain) return domain;
		const e = extent(values.flat());
		if (!e) return [0, 1];
		if (scale !== 'diverging') return e;
		const m = Math.max(Math.abs(e[0]), Math.abs(e[1])) || 1;
		return [-m, m];
	});

	// Cell text is picked per theme: --ink and --on-primary swap roles, and the ramp starts at surface-2.
	const theme = $derived(renderedTheme());

	const cells = $derived(
		rows.map((_, r) =>
			cols.map((_, c) => {
				const v = values[r]?.[c];
				if (typeof v !== 'number' || !Number.isFinite(v)) return null;
				const t = normalize(v, dom, scale);
				return {
					value: v,
					text: fmt(v),
					bg: heatColor(t, scale),
					ink: contrastInk(t, scale, theme)
				};
			})
		)
	);
	const textWidth = $derived(
		cells.reduce((m, row) => row.reduce((n, cell) => Math.max(n, cell?.text.length ?? 0), m), 0)
	);
	const printValues = $derived(showValues && cellW >= textWidth * 6.4 + 8 && cellH >= 16);
	const colEvery = $derived(
		Math.max(
			1,
			Math.floor(colLabelEvery ?? Math.ceil((longest(cols) * 6.2 + 8) / (cellW + GAP || 1)))
		)
	);

	const legendGradient = $derived(
		`linear-gradient(to right, ${Array.from({ length: 13 }, (_, i) => heatColor(i / 12, scale)).join(', ')})`
	);

	// The roving tab stop stays valid when the grid shrinks.
	const rover = $derived({ r: clamp(pos.r, 0, nr - 1), c: clamp(pos.c, 0, nc - 1) });
	const active = $derived(hover ?? focused);
	const tooltip = $derived.by(() => {
		if (!active || active.r >= nr || active.c >= nc) return null;
		const cell = cells[active.r][active.c];
		return {
			x: gutter + GAP + active.c * (cellW + GAP) + cellW / 2,
			y: HEADER + GAP + active.r * (cellH + GAP) + cellH / 2,
			title: `${rows[active.r]} \u00d7 ${cols[active.c]}`,
			rows: [{ label: 'Value', value: cell ? cell.text : MISSING }]
		};
	});

	const bounds = $derived(extent(values.flat()));
	const summary = $derived(
		nr === 0 || nc === 0
			? `${label}: no data.`
			: `${label}: ${nr} rows by ${nc} columns` +
					(bounds ? `, values from ${fmt(bounds[0])} to ${fmt(bounds[1])}` : ', no values') +
					'. Focus the grid and use the arrow keys to move between cells.'
	);

	const cellOf = (target: EventTarget | null): Pos | null => {
		const el = (target as Element | null)?.closest<HTMLElement>('[data-r]');
		return el ? { r: Number(el.dataset.r), c: Number(el.dataset.c) } : null;
	};

	function onfocusin(e: FocusEvent) {
		const p = cellOf(e.target);
		if (!p) return;
		pos = p;
		focused = (e.target as HTMLElement).matches(':focus-visible') ? p : null;
	}

	function onfocusout(e: FocusEvent) {
		if (!gridEl?.contains(e.relatedTarget as Node | null)) focused = null;
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.altKey || e.metaKey) return;
		let { r, c } = rover;
		switch (e.key) {
			case 'ArrowRight':
				c++;
				break;
			case 'ArrowLeft':
				c--;
				break;
			case 'ArrowDown':
				r++;
				break;
			case 'ArrowUp':
				r--;
				break;
			case 'PageDown':
				r += 5;
				break;
			case 'PageUp':
				r -= 5;
				break;
			case 'Home':
				c = 0;
				if (e.ctrlKey) r = 0;
				break;
			case 'End':
				c = nc - 1;
				if (e.ctrlKey) r = nr - 1;
				break;
			default:
				return;
		}
		e.preventDefault();
		r = clamp(r, 0, nr - 1);
		c = clamp(c, 0, nc - 1);
		pos = { r, c };
		gridEl?.querySelector<HTMLElement>(`[data-r="${r}"][data-c="${c}"]`)?.focus();
	}
</script>

<div class="relative min-w-0 {className}" {@attach size}>
	{#if width > 0 && nr > 0 && nc > 0}
		<!-- svelte-ignore a11y_interactive_supports_focus (the cells carry the roving tabindex) -->
		<div
			bind:this={gridEl}
			role="grid"
			aria-label={label}
			aria-rowcount={nr + 1}
			aria-colcount={nc + 1}
			class="flex flex-col"
			style:gap="{GAP}px"
			style:width="{gutter + GAP + gridW}px"
			onpointerover={(e) => (hover = cellOf(e.target))}
			onpointerleave={() => (hover = null)}
			{onfocusin}
			{onfocusout}
			{onkeydown}
		>
			<div
				role="row"
				aria-rowindex={1}
				class="grid"
				style:grid-template-columns={template}
				style:column-gap="{GAP}px"
				style:height="{HEADER}px"
			>
				<div role="columnheader"><span class="sr-only">Row</span></div>
				{#each cols as col, c (c)}
					<div role="columnheader" class="flex items-end justify-center pb-1">
						<span
							class={c % colEvery === 0
								? 'text-[11px] whitespace-nowrap text-ink-muted tabular-nums'
								: 'sr-only'}>{col}</span
						>
					</div>
				{/each}
			</div>
			{#each rows as row, r (r)}
				<div
					role="row"
					aria-rowindex={r + 2}
					class="grid"
					style:grid-template-columns={template}
					style:column-gap="{GAP}px"
				>
					<div role="rowheader" class="flex items-center justify-end overflow-hidden pr-2">
						<span class="truncate text-[11px] text-ink-muted">{row}</span>
					</div>
					{#each cols as col, c (c)}
						{@const cell = cells[r][c]}
						<div
							role="gridcell"
							tabindex={r === rover.r && c === rover.c ? 0 : -1}
							data-r={r}
							data-c={c}
							data-active={active?.r === r && active?.c === c}
							aria-label="{row}, {col}: {cell ? cell.text : 'no data'}"
							class="relative flex items-center justify-center rounded-xs after:pointer-events-none after:absolute after:inset-0 after:rounded-[inherit] after:border-[1.5px] after:border-ink after:opacity-0 after:transition-opacity after:duration-100 data-[active=true]:after:opacity-100"
							style:height="{cellH}px"
							style:background={cell?.bg}
						>
							{#if !cell}
								<span class="size-[3px] rounded-full bg-hairline"></span>
							{:else if printValues}
								<span
									class="pointer-events-none text-[11px] font-medium tabular-nums"
									style:color={cell.ink}>{cell.text}</span
								>
							{/if}
						</div>
					{/each}
				</div>
			{/each}
		</div>
		{#if legend}
			<div class="mt-3" style:margin-left="{gutter + GAP}px" style:width="{gridW}px">
				<div class="h-2 rounded-full" style:background={legendGradient} aria-hidden="true"></div>
				<div class="mt-1 flex justify-between text-[11px] text-ink-muted tabular-nums">
					<span>{legend.low}</span>
					<span>{legend.high}</span>
				</div>
			</div>
		{/if}
	{/if}
	{#if tooltip}
		<ChartTooltip
			x={tooltip.x}
			y={tooltip.y}
			{width}
			height={gridH}
			title={tooltip.title}
			rows={tooltip.rows}
			gap={cellW / 2 + 6}
		/>
	{/if}
	<p class="sr-only">{summary}</p>
</div>
