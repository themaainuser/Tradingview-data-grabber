<script lang="ts">
	import type { FearGreedBand, FearGreedPoint, FearGreedSnapshots } from '$lib/api/contracts';
	import { formatTime } from '$lib/charts/scale';
	import { BAND_FILL, BAND_TEXT, meterGradient } from '$lib/sentiment/bands';
	import { formatDelta } from '$lib/sentiment/stats';

	interface Props {
		current: FearGreedPoint;
		snapshots: FearGreedSnapshots;
		bands: readonly FearGreedBand[];
	}

	let { current, snapshots, bands }: Props = $props();

	const items = $derived([
		{ key: 'now', label: 'Now', point: current as FearGreedPoint | null, compare: false },
		{ key: 'yesterday', label: 'Yesterday', point: snapshots.yesterday, compare: true },
		{ key: 'week', label: '7 days ago', point: snapshots.week_ago, compare: true },
		{ key: 'month', label: '1 month ago', point: snapshots.month_ago, compare: true },
		{
			key: 'high',
			label: 'Year high',
			point: snapshots.year_high as FearGreedPoint | null,
			compare: true
		},
		{
			key: 'low',
			label: 'Year low',
			point: snapshots.year_low as FearGreedPoint | null,
			compare: true
		}
	]);
	const track = $derived(meterGradient(bands));
</script>

<ul
	class="grid grid-cols-2 gap-3 sm:grid-cols-3"
	aria-label="Fear and Greed readings for comparison"
>
	{#each items as item (item.key)}
		<li
			class="flex flex-col gap-2 rounded-xl p-5 {item.key === 'now'
				? 'bg-surface-2'
				: 'bg-surface-1'}"
			style:--card={item.key === 'now' ? 'var(--surface-2)' : 'var(--surface-1)'}
			data-testid="snapshot-{item.key}"
		>
			<p class="type-caption text-ink-muted">{item.label}</p>
			{#if item.point}
				<p class="type-display-md tabular-nums">{item.point.score}</p>
				<p class="flex items-center gap-2 type-body-sm" style:color={BAND_TEXT[item.point.band]}>
					<span
						class="size-2 shrink-0 rounded-full"
						style:background={BAND_FILL[item.point.band]}
						aria-hidden="true"
					></span>
					{item.point.label}
				</p>
				<p class="type-micro text-ink-muted tabular-nums">
					{formatTime(item.point.time, false)}
					{#if item.compare}
						<span class="block">{formatDelta(current.score - item.point.score)} since</span>
					{/if}
				</p>
				<!-- Where the reading sits on the 0-100 scale; the band colours are faint so the dot leads. -->
				<div class="mt-auto pt-3" aria-hidden="true" data-testid="meter-{item.key}">
					<div class="relative h-1.5 rounded-pill">
						<div class="absolute inset-0 rounded-pill opacity-40" style:background={track}></div>
						<span
							class="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-(--card)"
							style:left="{item.point.score}%"
							style:background={BAND_TEXT[item.point.band]}
						></span>
					</div>
				</div>
			{:else}
				<p class="type-display-md text-ink-muted" aria-label="No reading">&mdash;</p>
				<p class="type-micro text-ink-muted">No reading for that day</p>
			{/if}
		</li>
	{/each}
</ul>
