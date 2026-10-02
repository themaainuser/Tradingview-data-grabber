<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { Activity } from '$lib/api/trading';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { DASH, money, quantity, signedMoney, tone, when, words } from '$lib/trading/format';

	let { store }: { store: TradingStore } = $props();

	let category = $state<'all' | 'trade_activity' | 'non_trade_activity'>('all');
	let older = $state.raw<Activity[]>([]);
	let loadingMore = $state(false);

	const query = (extra: Record<string, string> = {}) => ({
		...(category === 'all' ? {} : { category }),
		...extra
	});
	onMount(() => {
		void store.loadActivities(query());
	});

	function choose(next: string) {
		category = next as typeof category;
		older = [];
		void store.loadActivities(query());
	}

	const newest = $derived(store.activities.data?.activities ?? []);
	const rows = $derived([...newest, ...older]);
	// Follows the newest page; "Load older activity" moves it on until a reload starts over.
	let token = $derived(store.activities.data?.next_page_token ?? null);

	async function more() {
		const from = older.at(-1)?.id ?? newest.at(-1)?.id;
		if (!from || !store.env) return;
		loadingMore = true;
		try {
			const response = await store.readActivities(query({ page_token: from }));
			older = [...older, ...(response?.activities ?? [])];
			token =
				response && response.activities.length > 0 ? (response.next_page_token ?? null) : null;
		} finally {
			loadingMore = false;
		}
	}

	function amount(a: Activity): string {
		if (a.net_amount !== null) return signedMoney(a.net_amount);
		if (a.qty !== null && a.price !== null) return money(a.qty * a.price);
		return DASH;
	}
</script>

<SectionCard
	id="activity"
	title="Activity"
	description="Fills and everything else that touched the account: dividends, fees, transfers. Newest first."
>
	{#snippet actions()}
		<ToggleGroup.Root
			type="single"
			size="sm"
			value={category}
			onValueChange={(v) => v && choose(v)}
			aria-label="Kind of activity"
		>
			<ToggleGroup.Item value="all">All</ToggleGroup.Item>
			<ToggleGroup.Item value="trade_activity">Fills</ToggleGroup.Item>
			<ToggleGroup.Item value="non_trade_activity">Other</ToggleGroup.Item>
		</ToggleGroup.Root>
	{/snippet}

	{#if store.activities.problem && !store.activities.data}
		<p class="type-body-sm text-coral-ink" role="alert">{store.activities.problem}</p>
	{:else if !store.activities.data}
		<Skeleton class="h-40 w-full rounded-lg" />
	{:else}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div
			class="max-w-full overflow-x-auto rounded-lg"
			role="region"
			aria-label="Activity table"
			tabindex="0"
		>
			<table class="w-full border-collapse type-body-sm" data-testid="activity-table">
				<thead>
					<tr class="border-b border-hairline text-left text-ink-muted">
						{#each ['When', 'Type', 'Symbol', 'Side', 'Qty', 'Price', 'Amount'] as heading (heading)}
							<th
								scope="col"
								class="px-3 py-2 font-medium whitespace-nowrap {['Qty', 'Price', 'Amount'].includes(
									heading
								)
									? 'text-right'
									: ''}">{heading}</th
							>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each rows as a (a.id)}
						<tr class="border-b border-hairline-soft last:border-0" data-testid="activity-row">
							<td class="px-3 py-2 whitespace-nowrap text-ink-muted tabular-nums">{when(a.time)}</td
							>
							<td class="px-3 py-2"
								>{a.activity_type ?? DASH}{#if a.activity_sub_type}<span class="ml-1 text-ink-muted"
										>· {words(a.activity_sub_type)}</span
									>{/if}</td
							>
							<td class="px-3 py-2 font-mono">{a.symbol ?? DASH}</td>
							<td
								class="px-3 py-2 {a.side === 'buy'
									? 'text-success-ink'
									: a.side === 'sell'
										? 'text-coral-ink'
										: ''}">{words(a.side)}</td
							>
							<td class="px-3 py-2 text-right tabular-nums">{quantity(a.qty)}</td>
							<td class="px-3 py-2 text-right tabular-nums">{money(a.price, true)}</td>
							<td class="px-3 py-2 text-right tabular-nums {tone(a.net_amount)}">{amount(a)}</td>
						</tr>
					{:else}
						<tr
							><td
								colspan="7"
								class="px-3 py-8 text-center text-ink-muted"
								data-testid="no-activity">Nothing yet.</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>
		{#if token}<Button
				type="button"
				variant="translucent"
				size="sm"
				class="w-fit"
				disabled={loadingMore}
				onclick={more}>{loadingMore ? 'Loading…' : 'Load older activity'}</Button
			>{/if}
	{/if}
</SectionCard>
