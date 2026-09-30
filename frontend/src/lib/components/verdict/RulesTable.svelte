<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import X from '@lucide/svelte/icons/x';
	import { Badge } from '$lib/components/ui/badge';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { VerdictRule } from '$lib/api/contracts';
	import {
		STATUS_TITLE,
		bps,
		count,
		fixed,
		pValue,
		sharpeWithSe,
		signedPct,
		statusNote
	} from '$lib/verdict/present';

	interface Props {
		rules: readonly VerdictRule[];
		minTrades: number;
	}

	let { rules, minTrades }: Props = $props();

	// The only orderings on offer are the fixed grid and trade count: never by performance.
	let order = $state<'grid' | 'trades'>('grid');
	const rows = $derived(
		order === 'grid'
			? rules
			: [...rules].sort((a, b) => b.trades - a.trades || rules.indexOf(a) - rules.indexOf(b))
	);
	const tested = $derived(rules.filter((r) => r.status === 'PASSED_GATE').length);

	const stressAt = (rule: VerdictRule, multiplier: number) =>
		rule.evidence?.stress.find((s) => s.multiplier === multiplier) ?? null;

	const checks = (rule: VerdictRule) =>
		rule.evidence
			? [
					{ key: 'bootstrap', label: 'Bootstrap', ok: rule.evidence.checks.bootstrap },
					{ key: 'dsr', label: 'DSR', ok: rule.evidence.checks.dsr },
					{ key: 'stress', label: '1.5\u00d7 costs', ok: rule.evidence.checks.stress }
				]
			: [];
</script>

<section
	class="grid grid-cols-[minmax(0,1fr)] gap-[15px]"
	aria-labelledby="rules-title"
	data-testid="rules-section"
>
	<div class="flex flex-wrap items-end gap-[15px]">
		<div class="grid min-w-0 flex-1 gap-1">
			<h2 id="rules-title" class="type-headline">Rules</h2>
			<p class="max-w-[68ch] type-caption text-pretty text-ink-muted">
				{tested} of {rules.length} rules traded at least {count(minTrades)} times. Rules below that get
				no Sharpe, p-value or DSR, and nothing here is ranked by performance.
			</p>
		</div>
		<ToggleGroup.Root
			type="single"
			size="sm"
			value={order}
			onValueChange={(v) => v && (order = v as typeof order)}
			aria-label="Row order"
		>
			<ToggleGroup.Item value="grid">Grid order</ToggleGroup.Item>
			<ToggleGroup.Item value="trades">Most trades</ToggleGroup.Item>
		</ToggleGroup.Root>
	</div>

	<!-- A horizontally scrollable region must be reachable by keyboard, so it takes focus. -->
	<!-- `relative` matters: sr-only text is absolutely positioned and would otherwise escape this clip and widen the page. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="relative overflow-x-auto rounded-lg bg-surface-1"
		role="region"
		aria-label="Rules table, scrolls sideways on narrow screens"
		tabindex="0"
	>
		<table class="w-full min-w-[56rem] text-left type-body-sm">
			<caption class="sr-only"
				>Every rule tried, with its trade count and, where it qualifies, its evidence</caption
			>
			<thead class="type-caption text-ink-muted">
				<tr class="border-b border-hairline">
					<th scope="col" class="px-3 py-3 font-medium">Rule</th>
					<th scope="col" class="px-3 py-3 font-medium">Status</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">Trades</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">In market</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">Sharpe &plusmn; SE</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">Adj. p</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">DSR</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">Net / trade</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">At 1.5&times; costs</th>
					<th scope="col" class="px-3 py-3 text-right font-medium">Break-even</th>
					<th scope="col" class="px-3 py-3 font-medium">Checks</th>
				</tr>
			</thead>
			<tbody class="tabular-nums">
				{#each rows as rule (rule.id)}
					{@const ev = rule.evidence}
					<tr
						class="border-b border-hairline-soft last:border-0"
						data-testid="rule-row"
						data-status={rule.status}
						data-candidate={ev?.candidate ? 'true' : undefined}
					>
						<th scope="row" class="px-3 py-3 align-top font-medium whitespace-nowrap">
							{rule.name}
							<span class="block type-micro font-normal text-ink-muted">{rule.family}</span>
						</th>
						<td class="px-3 py-3 align-top">
							<Badge
								variant={rule.status === 'PASSED_GATE'
									? 'success'
									: rule.status === 'ERROR'
										? 'destructive'
										: 'secondary'}>{STATUS_TITLE[rule.status]}</Badge
							>
						</td>
						<td class="px-3 py-3 text-right align-top whitespace-nowrap">{count(rule.trades)}</td>
						<td class="px-3 py-3 text-right align-top whitespace-nowrap"
							>{fixed(rule.exposure_pct, 0)}%</td
						>
						{#if ev}
							<td class="px-3 py-3 text-right align-top whitespace-nowrap"
								>{sharpeWithSe(ev.sharpe, ev.sharpe_se)}</td
							>
							<td class="px-3 py-3 text-right align-top whitespace-nowrap"
								>{pValue(ev.adjusted_p)}</td
							>
							<td class="px-3 py-3 text-right align-top whitespace-nowrap">{fixed(ev.dsr, 3)}</td>
							<td class="px-3 py-3 text-right align-top whitespace-nowrap"
								>{signedPct(ev.mean_trade_return_pct)}</td
							>
							<td class="px-3 py-3 text-right align-top whitespace-nowrap"
								>{signedPct(stressAt(rule, 1.5)?.mean_trade_return_pct)}</td
							>
							<td class="px-3 py-3 text-right align-top whitespace-nowrap">
								{bps(ev.break_even.round_trip_bps)}
								{#if ev.break_even.multiple !== null}
									<span class="block type-micro text-ink-muted"
										>{fixed(ev.break_even.multiple, 1)}&times; base cost</span
									>
								{/if}
							</td>
							<td class="px-3 py-3 align-top">
								<ul class="flex flex-wrap gap-1">
									{#each checks(rule) as check (check.key)}
										<li
											class="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-2 py-0.5 type-micro"
										>
											{#if check.ok}<Check class="size-3" aria-hidden="true" />{:else}<X
													class="size-3"
													aria-hidden="true"
												/>{/if}
											{check.label}
											<span class="sr-only">{check.ok ? 'passed' : 'failed'}</span>
										</li>
									{/each}
								</ul>
							</td>
						{:else}
							<td colspan="7" class="px-3 py-3 align-top text-ink-muted" data-testid="not-tested">
								<span class="type-caption text-pretty">{statusNote(rule, minTrades)}</span>
							</td>
						{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>
