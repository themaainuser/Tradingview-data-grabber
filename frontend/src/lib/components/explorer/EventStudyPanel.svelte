<script lang="ts">
	import { Switch } from '$lib/components/ui/switch';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import type { EventStudy } from '$lib/analysis/event-study';
	import { formatValue } from '$lib/format';

	interface Props {
		study: EventStudy;
		horizons: number[];
		onhorizons: (horizons: number[]) => void;
		onsetOnly: boolean;
		ononset: (value: boolean) => void;
	}

	let { study, horizons, onhorizons, onsetOnly, ononset }: Props = $props();

	// While the box is focused the user's draft wins; otherwise it mirrors the store (normalised).
	let draft = $state<string | null>(null);
	const text = $derived(draft ?? horizons.join(', '));

	function parseHorizons(value: string): number[] | null {
		const parsed = value
			.split(/[\s,]+/)
			.filter(Boolean)
			.map(Number);
		const valid =
			parsed.length > 0 &&
			parsed.length <= 8 &&
			parsed.every((n) => Number.isInteger(n) && n >= 1 && n <= 1000);
		return valid ? [...new Set(parsed)].sort((a, b) => a - b) : null;
	}

	const invalid = $derived(draft !== null && parseHorizons(draft) === null);

	function edit(value: string) {
		draft = value;
		const parsed = parseHorizons(value);
		if (parsed) onhorizons(parsed);
	}

	const pct = (v: number | null) => (v === null ? null : v * 100);
	const tone = (v: number | null) =>
		v === null ? '' : v > 0 ? 'text-positive' : v < 0 ? 'text-negative' : '';
</script>

<section class="grid gap-3" aria-label="Forward returns after matching bars">
	<header class="flex flex-wrap items-center gap-x-4 gap-y-2">
		<h2 class="type-body-sm">Forward returns after a match</h2>
		<span class="type-body text-ink-muted tabular-nums" data-testid="event-count">
			{study.events.toLocaleString('en-US')} events
		</span>
		<div class="ml-auto flex flex-wrap items-center gap-3">
			<div class="flex items-center gap-2">
				<Label for="horizons" class="type-caption">Horizons (bars)</Label>
				<Input
					id="horizons"
					class="h-8 w-36 tabular-nums"
					value={text}
					oninput={(e) => edit(e.currentTarget.value)}
					onblur={() => (draft = null)}
					aria-invalid={invalid}
				/>
			</div>
			<div class="flex items-center gap-2">
				<Switch id="onset" checked={onsetOnly} onCheckedChange={ononset} />
				<Label for="onset" class="type-caption">First bar of each run only</Label>
			</div>
		</div>
	</header>
	{#if invalid}
		<p class="type-caption text-gradient-coral" role="alert">
			Enter up to 8 whole numbers between 1 and 1000, separated by commas.
		</p>
	{/if}

	<div class="overflow-x-auto rounded-lg bg-canvas">
		<table class="w-full min-w-[44rem] type-body-sm tabular-nums">
			<thead class="type-caption text-ink-muted">
				<tr class="border-b">
					<th class="px-3 py-2 text-left font-medium">Horizon</th>
					<th class="px-3 py-2 text-right font-medium">N</th>
					<th class="px-3 py-2 text-right font-medium">Hit rate</th>
					<th class="px-3 py-2 text-right font-medium">Mean</th>
					<th class="px-3 py-2 text-right font-medium">Median</th>
					<th class="px-3 py-2 text-right font-medium">Worst</th>
					<th class="px-3 py-2 text-right font-medium">Best</th>
					<th class="px-3 py-2 text-right font-medium">All-bars mean</th>
					<th class="px-3 py-2 text-right font-medium">Excess</th>
					<th class="px-3 py-2 text-right font-medium">t-stat</th>
				</tr>
			</thead>
			<tbody>
				{#each study.horizons as h (h.horizon)}
					<tr class="border-b last:border-0">
						<td class="px-3 py-1.5">{h.horizon} bar{h.horizon === 1 ? '' : 's'}</td>
						<td class="px-3 py-1.5 text-right">{h.n.toLocaleString('en-US')}</td>
						<td class="px-3 py-1.5 text-right">{formatValue(pct(h.hitRate), 'pct')}</td>
						<td class="px-3 py-1.5 text-right {tone(h.mean)}">{formatValue(pct(h.mean), 'pct')}</td>
						<td class="px-3 py-1.5 text-right {tone(h.median)}"
							>{formatValue(pct(h.median), 'pct')}</td
						>
						<td class="px-3 py-1.5 text-right">{formatValue(pct(h.worst), 'pct')}</td>
						<td class="px-3 py-1.5 text-right">{formatValue(pct(h.best), 'pct')}</td>
						<td class="px-3 py-1.5 text-right">{formatValue(pct(h.baselineMean), 'pct')}</td>
						<td class="px-3 py-1.5 text-right {tone(h.excessMean)}"
							>{formatValue(pct(h.excessMean), 'pct')}</td
						>
						<td class="px-3 py-1.5 text-right">{formatValue(h.tStat, 'ratio')}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="type-caption text-pretty text-ink-muted">
		Returns run from the matching bar's close to the close N bars later. Nearby matches overlap, so
		the t-stat overstates confidence; enable “first bar of each run” to de-cluster. Costs and
		slippage are not included. Descriptive statistics, not trading advice.
	</p>
</section>
