<script lang="ts">
	import { BAND_FILL } from '$lib/sentiment/bands';
	import type { ZoneShare } from '$lib/sentiment/stats';

	interface Props {
		zones: readonly ZoneShare[];
	}

	let { zones }: Props = $props();

	const total = $derived(zones.reduce((sum, z) => sum + z.count, 0));
	const pct = (share: number) => `${(share * 100).toFixed(share > 0 && share < 0.1 ? 1 : 0)}%`;
</script>

{#if total === 0}
	<p class="type-body text-ink-muted" role="status">No readings in this range.</p>
{:else}
	<div class="grid gap-5" data-testid="zone-bar">
		<div
			class="flex h-3 w-full gap-0.5 overflow-hidden rounded-pill"
			role="img"
			aria-label="Share of days in each zone: {zones
				.filter((z) => z.count > 0)
				.map((z) => `${z.label} ${pct(z.share)}`)
				.join(', ')}"
		>
			{#each zones as zone (zone.key)}
				{#if zone.count > 0}
					<div
						class="h-full transition-[flex-grow] duration-150 ease-out"
						style:flex-grow={zone.count}
						style:flex-basis="0"
						style:min-width="3px"
						style:background={BAND_FILL[zone.key]}
					></div>
				{/if}
			{/each}
		</div>
		<ul class="grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-3">
			{#each zones as zone (zone.key)}
				<li class="flex items-center gap-2.5" data-testid="zone-{zone.key}">
					<span
						class="size-2.5 shrink-0 rounded-full"
						style:background={BAND_FILL[zone.key]}
						aria-hidden="true"
					></span>
					<span class="min-w-0">
						<span class="block truncate type-body-sm">{zone.label}</span>
						<span class="block type-caption text-ink-muted tabular-nums">
							{zone.count.toLocaleString('en-US')}
							{zone.count === 1 ? 'reading' : 'readings'} · {pct(zone.share)}
						</span>
					</span>
				</li>
			{/each}
		</ul>
	</div>
{/if}
