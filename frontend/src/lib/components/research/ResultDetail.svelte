<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { Button } from '$lib/components/ui/button';
	import { formatValue, type NumberFormat } from '$lib/format';
	import type { PerformanceMetrics, ResearchResult } from '$lib/api/contracts';

	interface Props {
		result: ResearchResult;
		onclose: () => void;
	}

	let { result, onclose }: Props = $props();

	const ROWS: { key: keyof PerformanceMetrics; label: string; format: NumberFormat }[] = [
		{ key: 'total_return_pct', label: 'Return', format: 'pct' },
		{ key: 'cagr_pct', label: 'CAGR', format: 'pct' },
		{ key: 'annualized_volatility_pct', label: 'Volatility', format: 'pct' },
		{ key: 'sharpe', label: 'Sharpe', format: 'ratio' },
		{ key: 'sortino', label: 'Sortino', format: 'ratio' },
		{ key: 'max_drawdown_pct', label: 'Max drawdown', format: 'pct' },
		{ key: 'calmar', label: 'Calmar', format: 'ratio' },
		{ key: 'trades', label: 'Trades', format: 'int' },
		{ key: 'win_rate_pct', label: 'Win rate', format: 'pct' },
		{ key: 'exposure_pct', label: 'Exposure', format: 'pct' }
	];

	const WINDOWS = [
		['full_sample', 'Full sample'],
		['in_sample', 'In-sample'],
		['forward', 'Forward']
	] as const;

	const day = (iso: string) => iso.slice(0, 10);
</script>

<section class="grid gap-4" aria-label="Strategy detail">
	<header class="flex items-start gap-2">
		<div class="min-w-0">
			<h2 class="truncate type-body font-medium">
				{result.name} <span class="font-normal text-ink-muted">on {result.symbol}</span>
			</h2>
			<p class="type-caption text-ink-muted">
				{result.family} · {Object.entries(result.parameters)
					.map(([k, v]) => `${k} ${v}`)
					.join(', ')}
			</p>
		</div>
		<Button
			variant="ghost"
			size="icon-sm"
			class="ml-auto"
			aria-label="Close detail"
			onclick={onclose}
		>
			<X aria-hidden="true" />
		</Button>
	</header>

	<div class="overflow-x-auto rounded-lg bg-canvas">
		<table class="w-full min-w-[28rem] type-body-sm tabular-nums">
			<thead class="type-caption text-ink-muted">
				<tr class="border-b">
					<th class="px-3 py-2 text-left font-medium">Metric</th>
					{#each WINDOWS as [, label] (label)}<th class="px-3 py-2 text-right font-medium"
							>{label}</th
						>{/each}
				</tr>
			</thead>
			<tbody>
				{#each ROWS as row (row.key)}
					<tr class="border-b last:border-0">
						<td class="px-3 py-1.5">{row.label}</td>
						{#each WINDOWS as [window] (window)}
							<td class="px-3 py-1.5 text-right"
								>{formatValue(result.metrics[window][row.key], row.format)}</td
							>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<div class="grid gap-2">
		<h3 class="type-body-sm">Forward folds</h3>
		{#if result.forward_folds.length === 0}
			<p class="type-body-sm text-pretty text-ink-muted">
				This capture is too short to include a forward window.
			</p>
		{:else}
			<div class="overflow-x-auto rounded-lg bg-canvas">
				<table class="w-full min-w-[28rem] type-body-sm tabular-nums">
					<thead class="type-caption text-ink-muted">
						<tr class="border-b">
							<th class="px-3 py-2 text-left font-medium">Fold</th>
							<th class="px-3 py-2 text-left font-medium">Period</th>
							<th class="px-3 py-2 text-right font-medium">Return</th>
							<th class="px-3 py-2 text-right font-medium">Sharpe</th>
							<th class="px-3 py-2 text-right font-medium">Max DD</th>
							<th class="px-3 py-2 text-right font-medium">Trades</th>
						</tr>
					</thead>
					<tbody>
						{#each result.forward_folds as fold, i (fold.start)}
							<tr class="border-b last:border-0">
								<td class="px-3 py-1.5">{i + 1}</td>
								<td class="px-3 py-1.5 text-ink-muted">{day(fold.start)} → {day(fold.end)}</td>
								<td
									class="px-3 py-1.5 text-right {(fold.metrics.total_return_pct ?? 0) >= 0
										? 'text-positive'
										: 'text-negative'}">{formatValue(fold.metrics.total_return_pct, 'pct')}</td
								>
								<td class="px-3 py-1.5 text-right">{formatValue(fold.metrics.sharpe, 'ratio')}</td>
								<td class="px-3 py-1.5 text-right"
									>{formatValue(fold.metrics.max_drawdown_pct, 'pct')}</td
								>
								<td class="px-3 py-1.5 text-right">{formatValue(fold.metrics.trades, 'int')}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
</section>
