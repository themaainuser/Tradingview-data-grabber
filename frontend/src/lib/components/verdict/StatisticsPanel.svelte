<script lang="ts">
	import type { VerdictReport } from '$lib/api/contracts';
	import { count, fixed, pClaim } from '$lib/verdict/present';

	interface Props {
		report: VerdictReport;
	}

	let { report }: Props = $props();

	const stats = $derived(report.statistics);
	const se = $derived(report.uncertainty);
	// Position on a 0..max track: the interval is shaded and the estimate is a marker.
	const max = $derived(
		stats ? Math.max(stats.effective_n.ledger_trials, stats.effective_n.high, 1) : 1
	);
	const at = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`;
</script>

<section
	class="grid grid-cols-[minmax(0,1fr)] gap-[15px]"
	aria-labelledby="stats-title"
	data-testid="statistics-section"
>
	<div class="grid gap-1">
		<h2 id="stats-title" class="type-headline">What the statistics say</h2>
		<p class="max-w-[68ch] type-caption text-pretty text-ink-muted">
			Computed only for rules that passed the trade-count gate, and deflated for how many rules were
			tried.
		</p>
	</div>

	<div class="grid gap-3 md:grid-cols-2">
		{#if !stats}
			<div class="rounded-xl bg-surface-1 p-5 md:col-span-2" data-testid="no-statistics">
				<p class="type-body text-pretty text-ink-muted">
					No statistics were computed: no rule passed the trade-count gate, so there is no
					significance test, deflated Sharpe ratio or overfitting estimate to report.
				</p>
			</div>
		{:else}
			<div class="grid content-start gap-3 rounded-xl bg-surface-1 p-5" data-testid="effective-n">
				<h3 class="type-body-sm">Effective number of independent rules</h3>
				<p class="type-display-md tabular-nums">{fixed(stats.effective_n.scaled_estimate, 1)}</p>
				<div class="relative h-2 rounded-pill bg-surface-2" aria-hidden="true">
					<div
						class="absolute inset-y-0 rounded-pill bg-ink-muted opacity-40"
						style:left={at(stats.effective_n.low)}
						style:width="calc({at(stats.effective_n.high)} - {at(stats.effective_n.low)})"
					></div>
					<div
						class="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-ink"
						style:left={at(stats.effective_n.scaled_estimate)}
					></div>
				</div>
				<p class="type-caption text-pretty text-ink-muted tabular-nums">
					{Math.round(stats.effective_n.level * 100)}% bootstrap interval {fixed(
						stats.effective_n.low,
						1
					)}
					to {fixed(stats.effective_n.high, 1)}, out of {count(stats.effective_n.ledger_trials)} rules
					tried. Similar rules count as one bet, so this is usually far below the raw count, and it is
					an estimate, not a fact.
				</p>
			</div>

			<div class="grid content-start gap-3 rounded-xl bg-surface-1 p-5" data-testid="reality-check">
				<h3 class="type-body-sm">Does the best rule beat luck?</h3>
				<p class="type-display-md tabular-nums">
					{pClaim(stats.reality_check.p_value)}
				</p>
				<p class="type-caption text-pretty text-ink-muted">
					{stats.reality_check.rejected ? 'Below' : 'Not below'}
					{stats.reality_check.alpha}: {stats.reality_check.rejected
						? 'the best rule beats exposure-matched passive holding by more than chance across'
						: 'the best rule does not stand out from exposure-matched passive holding across'}
					{count(stats.reality_check.rules_tested)}
					{stats.reality_check.rules_tested === 1 ? 'rule' : 'rules'} tested. Block bootstrap,
					{count(stats.reality_check.replicates)} resamples of about {count(
						stats.reality_check.mean_block_length
					)} bars, with a fixed seed so the answer does not change between clicks.
				</p>
			</div>

			<div
				class="grid content-start gap-3 rounded-xl bg-surface-1 p-5 md:col-span-2"
				data-testid="pbo"
			>
				<h3 class="type-body-sm">Probability of backtest overfitting</h3>
				{#if stats.pbo && stats.pbo.value !== null}
					<p class="flex flex-wrap items-baseline gap-3">
						<span class="type-display-md tabular-nums">{fixed(stats.pbo.value, 2)}</span>
						{#if stats.pbo.noisy}
							<span class="rounded-pill bg-surface-2 px-2.5 py-1 type-micro" data-testid="pbo-noisy"
								>Noisy at this sample length</span
							>
						{/if}
					</p>
					<p class="type-caption text-pretty text-ink-muted tabular-nums">
						How often the best rule in one half of the data ranks at or below the median in the
						other half: {count(stats.pbo.combinations)} splits of {count(stats.pbo.blocks)} blocks across
						{count(stats.pbo.rules)} rules. {stats.pbo.caveat}
					</p>
				{:else}
					<p class="type-caption text-pretty text-ink-muted">
						Not available: {stats.pbo_unavailable ?? 'not enough rules or bars.'}
					</p>
				{/if}
			</div>
		{/if}

		<div
			class="grid content-start gap-2 rounded-xl bg-surface-1 p-5 md:col-span-2"
			data-testid="uncertainty"
		>
			<h3 class="type-body-sm">How precise can any Sharpe be here?</h3>
			<p class="type-caption text-pretty text-ink-muted tabular-nums">
				With {count(se.research_bars)} research bars the annualised Sharpe has a standard error of about
				&plusmn;{fixed(se.sharpe_se_annualised_iid, 1)}, even if the true Sharpe is zero. The sealed
				{count(se.holdout_bars)}-bar holdout is wider still, about &plusmn;{fixed(
					se.holdout_sharpe_se_annualised_iid,
					1
				)}. {se.note}
			</p>
		</div>
	</div>
</section>
