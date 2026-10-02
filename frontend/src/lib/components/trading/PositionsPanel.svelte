<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import {
		DASH,
		fractionToPercent,
		money,
		quantity,
		signedMoney,
		signedPercent,
		tone
	} from '$lib/trading/format';
	import { kindOf } from '$lib/trading/order';
	import ClosePosition from './ClosePosition.svelte';
	import ConfirmAction from './ConfirmAction.svelte';

	let {
		store,
		ontrade
	}: { store: TradingStore; ontrade: (symbol: string, side: 'buy' | 'sell') => void } = $props();

	onMount(() => {
		void store.loadPositions();
	});

	let cancelFirst = $state(true);
	const positions = $derived(store.positions.data?.positions ?? []);
	const total = $derived(positions.reduce((sum, p) => sum + (p.unrealized_pl ?? 0), 0));
	const value = $derived(positions.reduce((sum, p) => sum + (p.market_value ?? 0), 0));
</script>

<SectionCard
	id="positions"
	title="Positions"
	description={positions.length > 0
		? `${positions.length} open · market value ${money(value)} · unrealized ${signedMoney(total)}`
		: 'What the account holds right now.'}
>
	{#snippet actions()}
		<ConfirmAction
			label="Close all positions"
			confirmLabel="Close every position"
			description="Every open position is closed with a market order, long and short."
			realMoney={store.realMoney}
			variant="destructive"
			disabled={store.busy > 0 || positions.length === 0}
			onconfirm={async () => void (await store.closeAllPositions(cancelFirst))}
		>
			<label class="flex items-center gap-2 type-caption"
				><Checkbox bind:checked={cancelFirst} aria-label="Cancel open orders first" /> Cancel open orders
				first</label
			>
		</ConfirmAction>
	{/snippet}

	{#if store.positions.problem && !store.positions.data}
		<p class="type-body-sm text-coral-ink" role="alert">{store.positions.problem}</p>
	{:else if !store.positions.data}
		<Skeleton class="h-40 w-full rounded-lg" />
	{:else}
		{#if store.positions.stale}<p class="type-caption text-ink-muted" role="status">
				Could not refresh: {store.positions.problem} Showing the last read.
			</p>{/if}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div
			class="max-w-full overflow-x-auto rounded-lg"
			role="region"
			aria-label="Positions table"
			tabindex="0"
		>
			<table class="w-full border-collapse type-body-sm" data-testid="positions-table">
				<thead>
					<tr class="border-b border-hairline text-left text-ink-muted">
						{#each ['Symbol', 'Side', 'Qty', 'Avg entry', 'Price', 'Market value', 'Unrealized', 'Today', ''] as heading (heading)}
							<th
								scope="col"
								class="px-3 py-2 font-medium whitespace-nowrap {[
									'Qty',
									'Avg entry',
									'Price',
									'Market value',
									'Unrealized',
									'Today'
								].includes(heading)
									? 'text-right'
									: ''}">{heading || 'Actions'}</th
							>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each positions as p (p.asset_id ?? p.symbol)}
						<tr
							class="border-b border-hairline-soft align-top last:border-0"
							data-testid="position-row"
						>
							<td class="px-3 py-2 font-mono font-medium">{p.symbol}</td>
							<td class="px-3 py-2">{p.side === 'short' ? 'Short' : 'Long'}</td>
							<td class="px-3 py-2 text-right tabular-nums">{quantity(p.qty)}</td>
							<td class="px-3 py-2 text-right tabular-nums">{money(p.avg_entry_price, true)}</td>
							<td class="px-3 py-2 text-right tabular-nums">{money(p.current_price, true)}</td>
							<td class="px-3 py-2 text-right tabular-nums">{money(p.market_value)}</td>
							<td class="px-3 py-2 text-right tabular-nums {tone(p.unrealized_pl)}"
								>{signedMoney(p.unrealized_pl)}
								<span class="text-xs">({signedPercent(fractionToPercent(p.unrealized_plpc))})</span
								></td
							>
							<td class="px-3 py-2 text-right tabular-nums {tone(p.change_today)}"
								>{signedPercent(fractionToPercent(p.change_today))}</td
							>
							<td class="px-3 py-2">
								<div class="flex flex-wrap items-start gap-2">
									<Button
										type="button"
										variant="translucent"
										size="xs"
										onclick={() => ontrade(p.symbol as string, p.side === 'short' ? 'buy' : 'sell')}
										>Trade</Button
									>
									<ClosePosition {store} position={p} />
									{#if kindOf(p.symbol ?? '') === 'us_option'}
										<ConfirmAction
											label="Exercise"
											confirmLabel="Exercise"
											description="Exercising converts the contract into the underlying shares. All the contracts you hold are exercised, and it cannot be undone."
											realMoney={store.realMoney}
											size="xs"
											onconfirm={async () => void (await store.exercise(p.symbol as string))}
										/>
										<ConfirmAction
											label="Let expire"
											confirmLabel="Do not exercise"
											description="Tells Alpaca not to exercise this contract automatically at expiry, even if it is in the money."
											realMoney={store.realMoney}
											size="xs"
											onconfirm={async () => void (await store.doNotExercise(p.symbol as string))}
										/>
									{/if}
								</div>
							</td>
						</tr>
					{:else}
						<tr
							><td
								colspan="9"
								class="px-3 py-8 text-center text-ink-muted"
								data-testid="no-positions">{DASH} No open positions.</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</SectionCard>
