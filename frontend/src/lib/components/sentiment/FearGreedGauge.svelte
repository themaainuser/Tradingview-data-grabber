<script lang="ts">
	import type { BandKey, FearGreedBand } from '$lib/api/contracts';
	import { formatTime } from '$lib/charts/scale';
	import { BAND_FILL, BAND_MEANING, BAND_TEXT } from '$lib/sentiment/bands';
	import { arcPath, GAUGE, needleRotation } from '$lib/sentiment/gauge';

	interface Props {
		score: number;
		label: string;
		band: BandKey;
		bands: readonly FearGreedBand[];
		/** UTC epoch seconds of the reading. */
		updated: number;
	}

	let { score, label, band, bands, updated }: Props = $props();

	// The needle animates only when the score changes after mount (a refresh): the first render
	// sets the final angle directly, so the page does not replay an entrance on load.
	const rotation = $derived(needleRotation(score));
	const { cx, cy, radius, stroke } = GAUGE;
</script>

<figure
	class="relative grid justify-items-center gap-3 overflow-hidden rounded-xl bg-surface-1 px-5 pt-[30px] pb-[30px]"
	style:--band={BAND_FILL[band]}
	data-testid="fear-greed-gauge"
>
	<!-- Atmosphere: a soft glow in the current band's colour, behind the dial. -->
	<div
		class="pointer-events-none absolute inset-0"
		style="background: radial-gradient(70% 55% at 50% 42%, color-mix(in oklab, var(--band) 18%, transparent), transparent 72%)"
		aria-hidden="true"
	></div>

	<svg
		viewBox="0 0 {GAUGE.width} {GAUGE.height}"
		class="relative w-full max-w-[420px]"
		role="img"
		aria-label="Fear and Greed gauge: {score} out of 100, {label}"
	>
		{#each bands as b (b.key)}
			<path
				d={arcPath(b.from, b.to)}
				fill="none"
				stroke={BAND_FILL[b.key]}
				stroke-width={stroke}
				opacity={b.key === band ? 1 : 0.36}
				data-band={b.key}
				data-active={b.key === band ? 'true' : undefined}
				style="transition: opacity 150ms ease-out"
			/>
		{/each}
		<text
			x={cx - radius}
			y={cy + 26}
			text-anchor="middle"
			class="fill-ink-muted tabular-nums"
			font-size="12">0</text
		>
		<text
			x={cx + radius}
			y={cy + 26}
			text-anchor="middle"
			class="fill-ink-muted tabular-nums"
			font-size="12">100</text
		>
		<g
			data-testid="gauge-needle"
			style:transform="rotate({rotation}deg)"
			style:transform-origin="{cx}px {cy}px"
			style="transition: transform 300ms cubic-bezier(0.2, 0, 0, 1)"
		>
			<polygon points="{cx - 3},{cy} {cx},{cy - 124} {cx + 3},{cy}" fill="var(--ink)" />
		</g>
		<circle {cx} {cy} r="11" fill="var(--ink)" />
		<circle {cx} {cy} r="4.5" fill="var(--surface-1)" />
	</svg>

	<div class="relative grid justify-items-center gap-1.5 text-center">
		<p class="type-display-lg tabular-nums" data-testid="gauge-score">{score}</p>
		<p class="type-headline" style:color={BAND_TEXT[band]} data-testid="gauge-label">{label}</p>
		<p class="max-w-[34ch] type-caption text-pretty text-ink-muted">{BAND_MEANING[band]}</p>
		<p class="type-micro text-ink-muted tabular-nums">
			Reading from {formatTime(updated, true)} UTC
		</p>
	</div>
</figure>
