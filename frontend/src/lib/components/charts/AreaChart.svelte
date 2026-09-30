<script lang="ts">
	import {
		areaPath,
		bisectTime,
		clamp,
		columnDecimate,
		extent,
		formatNumber,
		linePath,
		mergeExtents,
		padDomain,
		showsTimeOfDay,
		stepIndex,
		timeTicks
	} from '$lib/charts/chart-math';
	import { formatAxis, formatTime, niceTicks } from '$lib/charts/scale';
	import { MISSING } from '$lib/format';
	import ChartTooltip from './ChartTooltip.svelte';
	import { measure } from './measure';
	import type { AreaBand, AreaSeries } from './types';

	interface Props {
		/** UTC epoch seconds, ascending; every series has one value per entry. */
		time: readonly number[];
		series: readonly AreaSeries[];
		/** Horizontal bands on the left axis, drawn behind the series. */
		bands?: readonly AreaBand[];
		/** Default: data extent plus 6% padding. */
		leftDomain?: [number, number];
		rightDomain?: [number, number];
		/** Reference line on the left axis and fill origin of left-axis areas (default: domain minimum). */
		baseline?: number;
		leftFormat?: (value: number) => string;
		rightFormat?: (value: number) => string;
		height?: number;
		/** Accessible name of the chart. */
		label: string;
		class?: string;
	}

	let {
		time,
		series,
		bands = [],
		leftDomain,
		rightDomain,
		baseline,
		leftFormat,
		rightFormat,
		height = 280,
		label,
		class: className = ''
	}: Props = $props();

	const uid = $props.id();
	const TOP = 12;
	const BOTTOM = 26;

	let width = $state(0);
	let cursor = $state<number | null>(null);
	let byKeyboard = $state(false);
	let svgEl = $state<SVGSVGElement>();
	const size = measure((w) => (width = w));

	const n = $derived(time.length);
	const plotH = $derived(Math.max(10, height - TOP - BOTTOM));
	const sideOf = (s: AreaSeries) => s.axis ?? 'left';
	const hasRight = $derived(series.some((s) => sideOf(s) === 'right'));

	// One pass per series over its values, reused for domains and the screen-reader summary.
	const stats = $derived(
		series.map((s) => {
			let last: number | null = null;
			for (let i = s.values.length - 1; i >= 0; i--) {
				const v = s.values[i];
				if (typeof v === 'number' && Number.isFinite(v)) {
					last = v;
					break;
				}
			}
			return { extent: extent(s.values), last };
		})
	);

	function domainOf(
		side: 'left' | 'right',
		explicit: [number, number] | undefined,
		include?: number
	): [number, number] {
		if (explicit && explicit[1] > explicit[0]) return explicit;
		const parts = series.flatMap((s, i) => (sideOf(s) === side ? [stats[i].extent] : []));
		if (include !== undefined) parts.push([include, include]);
		const e = mergeExtents(parts);
		return e ? padDomain(e[0], e[1]) : [0, 1];
	}
	const leftDom = $derived(domainOf('left', leftDomain, baseline));
	const rightDom = $derived(domainOf('right', rightDomain));

	const yScale = (dom: readonly [number, number]) => (v: number) =>
		clamp((1 - (v - dom[0]) / (dom[1] - dom[0])) * plotH, -1e4, 1e4);
	const yLeft = $derived(yScale(leftDom));
	const yRight = $derived(yScale(rightDom));

	function axisTicks(dom: readonly [number, number], format?: (v: number) => string) {
		const ticks = niceTicks(dom[0], dom[1], Math.max(2, Math.floor(plotH / 44)));
		const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
		return ticks.map((value) => ({
			value,
			text: format ? format(value) : formatAxis(value, step)
		}));
	}
	const labelSpace = (ticks: readonly { text: string }[]) =>
		ticks.reduce((m, t) => Math.max(m, t.text.length), 0) * 6.6 + 14;
	const leftTicks = $derived(axisTicks(leftDom, leftFormat));
	const rightTicks = $derived(hasRight ? axisTicks(rightDom, rightFormat) : []);
	const marginLeft = $derived(Math.max(32, labelSpace(leftTicks)));
	const marginRight = $derived(hasRight ? Math.max(32, labelSpace(rightTicks)) : 12);
	const plotW = $derived(Math.max(10, width - marginLeft - marginRight));

	const t0 = $derived(n ? time[0] : 0);
	const t1 = $derived(n ? time[n - 1] : 1);
	const xOf = $derived((t: number) => (t1 > t0 ? ((t - t0) / (t1 - t0)) * plotW : plotW / 2));
	const intraday = $derived(showsTimeOfDay(t0, t1));

	const xTicks = $derived.by(() => {
		const half = intraday ? 52 : 32;
		const count = Math.max(1, Math.floor(plotW / (half * 2 + 20)));
		return timeTicks(t0, t1, count).map((t) => {
			const x = xOf(t);
			const anchor = x < half ? 'start' : x > plotW - half ? 'end' : 'middle';
			return { x, anchor, text: formatTime(t, intraday) };
		});
	});

	const drawn = $derived(
		series.map((s, k) => {
			const right = sideOf(s) === 'right';
			const dom = right ? rightDom : leftDom;
			const y = right ? yRight : yLeft;
			const x = (i: number) => xOf(time[i]);
			const indices = columnDecimate(time, s.values, plotW);
			const line = linePath(indices, s.values, x, y);
			if ((s.kind ?? 'line') !== 'area') return { s, k, line, area: '', peakY: 0, baseY: 0 };
			const origin = !right && baseline !== undefined ? baseline : dom[0];
			const baseY = clamp(y(origin), 0, plotH);
			let peakY = baseY;
			for (const i of indices) {
				const v = s.values[i];
				if (typeof v !== 'number' || !Number.isFinite(v)) continue;
				const py = clamp(y(v), 0, plotH);
				if (Math.abs(py - baseY) > Math.abs(peakY - baseY)) peakY = py;
			}
			return { s, k, line, area: areaPath(indices, s.values, x, y, baseY), peakY, baseY };
		})
	);

	const drawnBands = $derived(
		bands.flatMap((b, i) => {
			const top = clamp(yLeft(Math.max(b.from, b.to)), 0, plotH);
			const bottom = clamp(yLeft(Math.min(b.from, b.to)), 0, plotH);
			return bottom - top > 0 ? [{ i, top, bottom, band: b }] : [];
		})
	);

	const baselineY = $derived(
		baseline !== undefined && baseline >= leftDom[0] && baseline <= leftDom[1]
			? yLeft(baseline)
			: null
	);

	const formatFor = (s: AreaSeries) =>
		(sideOf(s) === 'right' ? rightFormat : leftFormat) ?? formatNumber;
	const show = (s: AreaSeries, v: number | null | undefined) =>
		typeof v === 'number' && Number.isFinite(v) ? formatFor(s)(v) : MISSING;
	const whenText = (t: number) => `${formatTime(t, intraday)}${intraday ? ' UTC' : ''}`;

	const tooltip = $derived(
		cursor === null || cursor >= n
			? null
			: {
					x: marginLeft + xOf(time[cursor]),
					title: whenText(time[cursor]),
					rows: series.map((s) => ({
						label: s.label,
						color: s.color,
						value: show(s, s.values[cursor as number])
					}))
				}
	);
	const readout = $derived(
		byKeyboard && tooltip
			? `${tooltip.title}. ${tooltip.rows.map((r) => `${r.label} ${r.value}`).join(', ')}`
			: ''
	);
	const summary = $derived(
		n === 0
			? `${label}: no data.`
			: `${label}. ${n} points from ${whenText(t0)} to ${whenText(t1)}. ` +
					series
						.map((s, i) => {
							const e = stats[i].extent;
							return e
								? `${s.label}: latest ${show(s, stats[i].last)}, low ${show(s, e[0])}, high ${show(s, e[1])}.`
								: `${s.label}: no data.`;
						})
						.join(' ') +
					' Focus the chart and use the arrow keys to read values.'
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
		cursor = bisectTime(time, t0 + (px / plotW) * (t1 - t0));
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
			cursor = n - 1;
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
				<defs>
					<clipPath id="{uid}-clip">
						<rect x="-2" y="-2" width={plotW + 4} height={plotH + 4} />
					</clipPath>
					{#each drawn as d (d.s.key)}
						{#if d.area}
							<linearGradient
								id="{uid}-fill-{d.k}"
								gradientUnits="userSpaceOnUse"
								x1="0"
								x2="0"
								y1={d.peakY}
								y2={d.peakY === d.baseY ? d.baseY + 1 : d.baseY}
							>
								<stop offset="0" style:stop-color={d.s.color} style:stop-opacity="0.32" />
								<stop offset="1" style:stop-color={d.s.color} style:stop-opacity="0" />
							</linearGradient>
						{/if}
					{/each}
				</defs>
				<g transform="translate({marginLeft} {TOP})">
					{#if n > 0}
						{#each leftTicks as tick (tick.value)}
							<line
								class="stroke-hairline"
								x1="0"
								x2={plotW}
								y1={yLeft(tick.value)}
								y2={yLeft(tick.value)}
								shape-rendering="crispEdges"
							/>
							<text
								class="fill-ink-muted text-[11px] tabular-nums"
								x="-8"
								y={yLeft(tick.value)}
								text-anchor="end"
								dominant-baseline="central">{tick.text}</text
							>
						{/each}
						{#each rightTicks as tick (tick.value)}
							<text
								class="fill-ink-muted text-[11px] tabular-nums"
								x={plotW + 8}
								y={yRight(tick.value)}
								dominant-baseline="central">{tick.text}</text
							>
						{/each}
						{#each xTicks as tick (tick.x)}
							<line
								class="stroke-hairline-soft"
								x1={tick.x}
								x2={tick.x}
								y1="0"
								y2={plotH}
								shape-rendering="crispEdges"
							/>
							<text
								class="fill-ink-muted text-[11px] tabular-nums"
								x={tick.x}
								y={plotH + 17}
								text-anchor={tick.anchor}>{tick.text}</text
							>
						{/each}

						{#each drawnBands as b (b.i)}
							<rect
								data-band={b.i}
								x="0"
								y={b.top}
								width={plotW}
								height={b.bottom - b.top}
								fill-opacity="0.14"
								style:fill={b.band.color}
							/>
							{#if b.band.label}
								<text
									class="fill-ink-muted text-[11px]"
									x={plotW - 6}
									y={(b.top + b.bottom) / 2}
									text-anchor="end"
									dominant-baseline="central">{b.band.label}</text
								>
							{/if}
						{/each}

						{#if baselineY !== null}
							<line
								class="stroke-ink-muted"
								x1="0"
								x2={plotW}
								y1={baselineY}
								y2={baselineY}
								stroke-dasharray="3 3"
								stroke-opacity="0.6"
							/>
						{/if}

						<g clip-path="url(#{uid}-clip)">
							{#each drawn as d (d.s.key)}
								{#if d.area}
									<path
										data-series={d.s.key}
										data-kind="area"
										d={d.area}
										style:fill="url(#{uid}-fill-{d.k})"
									/>
								{/if}
								<path
									data-series={d.s.key}
									data-kind="line"
									d={d.line}
									fill="none"
									stroke-width="1.75"
									stroke-linejoin="round"
									stroke-linecap="round"
									stroke-dasharray={d.s.dashed ? '5 4' : undefined}
									style:stroke={d.s.color}
								/>
							{/each}
						</g>

						{#if tooltip && cursor !== null}
							{@const cx = tooltip.x - marginLeft}
							<line
								data-cursor
								class="stroke-ink-muted"
								x1={cx}
								x2={cx}
								y1="0"
								y2={plotH}
								stroke-opacity="0.7"
								shape-rendering="crispEdges"
							/>
							<g clip-path="url(#{uid}-clip)">
								{#each series as s (s.key)}
									{@const v = s.values[cursor]}
									{#if typeof v === 'number' && Number.isFinite(v)}
										<circle
											{cx}
											cy={(sideOf(s) === 'right' ? yRight : yLeft)(v)}
											r="4"
											stroke-width="2"
											style:fill={s.color}
											style:stroke="var(--chart-bg)"
										/>
									{/if}
								{/each}
							</g>
						{/if}
					{/if}
				</g>
			</svg>
		{:else}
			<div style:height="{height}px"></div>
		{/if}
	</div>
	{#if tooltip}
		<ChartTooltip
			x={tooltip.x}
			y={TOP + 4}
			{width}
			{height}
			title={tooltip.title}
			rows={tooltip.rows}
			hang
		/>
	{/if}
	<p class="sr-only">{summary}</p>
	<p class="sr-only" aria-live="polite" aria-atomic="true">{readout}</p>
</div>
