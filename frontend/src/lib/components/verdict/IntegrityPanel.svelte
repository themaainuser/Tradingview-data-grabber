<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import type { VerdictReport } from '$lib/api/contracts';
	import { count, fixed } from '$lib/verdict/present';

	interface Props {
		report: VerdictReport;
	}

	let { report }: Props = $props();

	const integrity = $derived(report.integrity);
	const gap = $derived(integrity.close_to_open_gap_bps);
	const items = $derived([
		{
			key: 'shift',
			ok: integrity.signal_shift_verified,
			text: 'Signals are shifted one bar before any fill: a signal on a bar\u2019s close is filled at the next bar\u2019s open.'
		},
		{
			key: 'probe',
			ok: integrity.lookahead_probe.passed,
			text: `Look-ahead probe: all ${count(integrity.lookahead_probe.rules_checked)} rules give the same signals on data cut at bar ${count(integrity.lookahead_probe.truncation_bar)} as on the full window, so no rule uses a later bar.`
		}
	]);
</script>

<section
	class="grid grid-cols-[minmax(0,1fr)] gap-[15px]"
	aria-labelledby="integrity-title"
	data-testid="integrity-section"
>
	<h2 id="integrity-title" class="type-headline">Integrity checks</h2>
	<div class="grid gap-3 rounded-xl bg-surface-1 p-5">
		<ul class="grid gap-2">
			{#each items as item (item.key)}
				<li class="flex items-start gap-3 type-body-sm">
					{#if item.ok}
						<Check class="mt-0.5 size-4 shrink-0 text-success-ink" aria-hidden="true" />
						<span class="sr-only">Passed:</span>
					{:else}
						<TriangleAlert class="mt-0.5 size-4 shrink-0 text-coral-ink" aria-hidden="true" />
						<span class="sr-only">Failed:</span>
					{/if}
					<span class="text-pretty">{item.text}</span>
				</li>
			{/each}
		</ul>
		<dl class="grid grid-cols-2 gap-x-5 gap-y-3 tabular-nums sm:grid-cols-4">
			<div>
				<dt class="type-caption text-ink-muted">Fill model</dt>
				<dd class="type-body-sm">
					{integrity.fill_model === 'next_open' ? 'Next bar\u2019s open' : integrity.fill_model}
				</dd>
			</div>
			<div>
				<dt class="type-caption text-ink-muted">Close to next open, mean</dt>
				<dd class="type-body-sm">{fixed(gap.mean_abs, 3)} bps</dd>
			</div>
			<div>
				<dt class="type-caption text-ink-muted">Close to next open, max</dt>
				<dd class="type-body-sm">{fixed(gap.max_abs, 2)} bps</dd>
			</div>
			<div>
				<dt class="type-caption text-ink-muted">Research data fingerprint</dt>
				<dd class="font-mono type-body-sm">{integrity.research_fingerprint}</dd>
			</div>
		</dl>
		<p class="type-caption text-pretty text-ink-muted">
			For a market that trades around the clock the next open is almost the same price as the last
			close, so the fill model changes little here. It matters for instruments that gap.
			{report.settings.periods_per_year_inferred
				? `Periods per year was inferred as ${count(Math.round(report.settings.periods_per_year))} from the bar spacing, assuming continuous trading.`
				: `Periods per year was set to ${count(report.settings.periods_per_year)}.`}
		</p>
	</div>
</section>
