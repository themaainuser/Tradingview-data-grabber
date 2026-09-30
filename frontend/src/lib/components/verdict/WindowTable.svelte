<script lang="ts">
	import type { RuleWindow } from '$lib/api/contracts';
	import { count, fixed, sharpeWithSe, signedPct } from '$lib/verdict/present';

	interface Props {
		rules: readonly RuleWindow[];
		/** Accessible name of the table. */
		label: string;
	}

	let { rules, label }: Props = $props();
</script>

<!-- A horizontally scrollable region must be reachable by keyboard, so it takes focus. -->
<!-- `relative` matters: sr-only text is absolutely positioned and would otherwise escape this clip and widen the page. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="relative overflow-x-auto rounded-lg bg-canvas"
	role="region"
	aria-label="{label}, scrolls sideways on narrow screens"
	tabindex="0"
>
	<table class="w-full min-w-[40rem] text-left type-body-sm">
		<caption class="sr-only">{label}</caption>
		<thead class="type-caption text-ink-muted">
			<tr class="border-b border-hairline">
				<th scope="col" class="px-3 py-3 font-medium">Rule</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">Trades</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">In market</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">Net return</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">Buy and hold</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">Sharpe &plusmn; SE</th>
				<th scope="col" class="px-3 py-3 text-right font-medium">Net / trade</th>
			</tr>
		</thead>
		<tbody class="tabular-nums">
			{#each rules as r (r.id)}
				<tr class="border-b border-hairline-soft last:border-0" data-testid="window-row">
					<th scope="row" class="px-3 py-3 font-medium whitespace-nowrap">{r.name}</th>
					<td class="px-3 py-3 text-right">{count(r.trades)}</td>
					<td class="px-3 py-3 text-right">{fixed(r.exposure_pct, 0)}%</td>
					<td class="px-3 py-3 text-right">{signedPct(r.net_return_pct)}</td>
					<td class="px-3 py-3 text-right">{signedPct(r.buy_hold_return_pct)}</td>
					<td class="px-3 py-3 text-right">{sharpeWithSe(r.sharpe, r.sharpe_se)}</td>
					<td class="px-3 py-3 text-right">{signedPct(r.mean_trade_return_pct)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
