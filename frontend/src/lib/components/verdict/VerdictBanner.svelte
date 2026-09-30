<script lang="ts">
	import type { VerdictReport } from '$lib/api/contracts';
	import {
		VERDICT_DOT,
		VERDICT_MEANING,
		VERDICT_TITLE,
		count,
		utc,
		withRuleNames
	} from '$lib/verdict/present';

	interface Props {
		report: VerdictReport;
	}

	let { report }: Props = $props();

	const label = $derived(report.verdict.label);
	const facts = $derived([
		{ term: 'Research bars', detail: count(report.data.research_bars) },
		{
			term: 'Research window',
			detail: `${utc(report.data.research_start, false)} to ${utc(report.data.research_end, false)}`
		},
		{ term: 'Rules tried on this dataset', detail: count(report.ledger.trials_dataset) },
		{ term: 'Run at', detail: utc(report.created_at) }
	]);
</script>

<section
	class="relative grid gap-5 overflow-hidden rounded-xl bg-surface-1 p-[30px]"
	style:--tone={VERDICT_DOT[label]}
	aria-labelledby="verdict-title"
	data-testid="verdict-banner"
	data-label={label}
>
	<!-- Atmosphere: a soft glow in the verdict's colour, behind the text. -->
	<div
		class="pointer-events-none absolute inset-0"
		style="background: radial-gradient(60% 120% at 0% 0%, color-mix(in oklab, var(--tone) 14%, transparent), transparent 70%)"
		aria-hidden="true"
	></div>

	<div class="relative grid gap-2">
		<p class="type-caption text-ink-muted">Verdict</p>
		<h2 id="verdict-title" class="flex items-center gap-3 type-display-md">
			<span class="size-3.5 shrink-0 rounded-full" style:background="var(--tone)" aria-hidden="true"
			></span>
			<span data-testid="verdict-label">{VERDICT_TITLE[label]}</span>
		</h2>
	</div>

	<p class="relative max-w-[62ch] type-body-lg text-pretty" data-testid="verdict-headline">
		{withRuleNames(report.verdict.headline, report.rules)}
	</p>
	<p class="relative max-w-[62ch] type-body text-pretty text-ink-muted">{VERDICT_MEANING[label]}</p>

	{#if report.verdict.reasons.length}
		<ul class="relative grid max-w-[68ch] list-disc gap-1.5 pl-5 type-body-sm text-ink-muted">
			{#each report.verdict.reasons as reason (reason)}
				<li class="text-pretty">{withRuleNames(reason, report.rules)}</li>
			{/each}
		</ul>
	{/if}

	<dl class="relative grid grid-cols-2 gap-x-5 gap-y-3 tabular-nums sm:grid-cols-4">
		{#each facts as fact (fact.term)}
			<div>
				<dt class="type-caption text-ink-muted">{fact.term}</dt>
				<dd class="type-body-sm">{fact.detail}</dd>
			</div>
		{/each}
	</dl>
</section>
