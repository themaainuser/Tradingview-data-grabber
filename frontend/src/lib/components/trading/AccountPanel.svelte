<script lang="ts">
	import { onMount } from 'svelte';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import LineChart from '$lib/components/app/LineChart.svelte';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { LineSeries } from '$lib/charts/line-controller';
	import type { TradingStore, ViewName } from '$lib/state/trading.svelte';
	import {
		DASH,
		fractionToPercent,
		money,
		quantity,
		signedMoney,
		signedPercent,
		tone
	} from '$lib/trading/format';

	let { store, ongo }: { store: TradingStore; ongo: (view: ViewName) => void } = $props();

	const PERIODS = [
		{ id: '1D', label: '1 day', timeframe: '5Min' },
		{ id: '1W', label: '1 week', timeframe: '1H' },
		{ id: '1M', label: '1 month', timeframe: '1D' },
		{ id: '3M', label: '3 months', timeframe: '1D' },
		{ id: '1A', label: '1 year', timeframe: '1D' }
	] as const;
	let period = $state<(typeof PERIODS)[number]['id']>('1M');

	onMount(() => {
		void store.loadHistory(period, PERIODS.find((p) => p.id === period)!.timeframe);
	});

	function choose(id: string) {
		const next = PERIODS.find((p) => p.id === id);
		if (!next) return;
		period = next.id;
		void store.loadHistory(next.id, next.timeframe);
	}

	const account = $derived(store.account.data);
	const history = $derived(store.history.data);
	const points = $derived(
		history
			? history.timestamp
					.map((t, i) => ({
						t,
						equity: history.equity[i],
						pl: history.profit_loss[i],
						plpc: history.profit_loss_pct[i]
					}))
					.filter((p) => p.equity !== null)
			: []
	);
	const series = $derived<LineSeries[]>(
		points.length > 1
			? [
					{
						key: 'equity',
						label: 'Equity',
						color: '--chart-1',
						time: Float64Array.from(points.map((p) => p.t)),
						values: Float64Array.from(points.map((p) => p.equity as number))
					}
				]
			: []
	);
	const last = $derived(points.at(-1) ?? null);

	const stats = $derived(
		account
			? [
					{ id: 'equity', label: 'Equity', value: money(account.equity) },
					{
						id: 'day',
						label: 'Today',
						value: signedMoney(account.day_change),
						sub: signedPercent(account.day_change_percent),
						tone: tone(account.day_change)
					},
					{ id: 'cash', label: 'Cash', value: money(account.cash) },
					{ id: 'power', label: 'Buying power', value: money(account.buying_power) },
					{ id: 'long', label: 'Long market value', value: money(account.long_market_value) },
					{ id: 'short', label: 'Short market value', value: money(account.short_market_value) },
					{
						id: 'multiplier',
						label: 'Margin multiplier',
						value: account.multiplier === null ? DASH : `${quantity(account.multiplier)}×`
					},
					{ id: 'status', label: 'Account status', value: account.status ?? DASH }
				]
			: []
	);
</script>

<div class="grid min-w-0 gap-5">
	{#if store.account.problem && !account}
		<p class="rounded-lg bg-surface-1 p-4 type-body-sm text-coral-ink" role="alert">
			{store.account.problem}
		</p>
	{:else if !account}
		<div class="grid gap-3" role="status">
			<span class="sr-only">Loading the account…</span><Skeleton class="h-28 w-full rounded-xl" />
		</div>
	{:else}
		{#if account.trading_blocked || account.account_blocked || account.trade_suspended_by_user}
			<div
				class="flex flex-wrap items-center gap-2 rounded-xl bg-coral-ink/15 p-4 type-body-sm text-coral-ink"
				role="alert"
				data-testid="account-blocked"
			>
				<TriangleAlert class="size-4 shrink-0" aria-hidden="true" />
				{#if account.account_blocked}The account is blocked.
				{:else if account.trading_blocked}Trading is blocked on this account.
				{:else}New orders are suspended in the settings.
					<button type="button" class="underline" onclick={() => ongo('settings')}
						>Open the settings</button
					>
				{/if}
			</div>
		{/if}
		{#if store.account.stale}<p class="type-caption text-ink-muted" role="status">
				Could not refresh: {store.account.problem} These figures are from the last successful read.
			</p>{/if}
		<dl class="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="account-stats">
			{#each stats as s (s.id)}
				<div class="grid gap-1 rounded-xl bg-surface-1 p-4" data-testid="stat-{s.id}">
					<dt class="type-caption text-ink-muted">{s.label}</dt>
					<dd class="type-headline tabular-nums {s.tone ?? ''}">
						{s.value}{#if s.sub}<span class="ml-2 type-body-sm">{s.sub}</span>{/if}
					</dd>
				</div>
			{/each}
		</dl>
	{/if}

	<SectionCard
		id="equity-curve"
		title="Equity"
		description={last
			? `${signedMoney(last.pl)} (${signedPercent(fractionToPercent(last.plpc))}) over the period`
			: 'How the account value moved.'}
	>
		{#snippet actions()}
			<ToggleGroup.Root
				type="single"
				size="sm"
				value={period}
				onValueChange={(v) => v && choose(v)}
				aria-label="Period"
			>
				{#each PERIODS as p (p.id)}<ToggleGroup.Item value={p.id}>{p.label}</ToggleGroup.Item
					>{/each}
			</ToggleGroup.Root>
		{/snippet}
		{#if series.length > 0}
			<LineChart {series} label="Account equity over the selected period" />
		{:else if store.history.state === 'loading' || store.history.state === 'idle'}
			<Skeleton class="h-72 w-full rounded-lg" />
		{:else}
			<p class="type-body-sm text-ink-muted" data-testid="no-history">
				{store.history.problem ?? 'There is not enough history to draw a curve yet.'}
			</p>
		{/if}
	</SectionCard>
</div>
