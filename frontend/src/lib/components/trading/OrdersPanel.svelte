<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import type { Order } from '$lib/api/trading';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { DASH, money, quantity, statusTone, when, words } from '$lib/trading/format';
	import ConfirmAction from './ConfirmAction.svelte';
	import Field from './Field.svelte';

	let { store }: { store: TradingStore } = $props();

	onMount(() => {
		void store.loadOrders();
	});

	interface Row {
		order: Order;
		leg: boolean;
	}

	const rows = $derived<Row[]>(
		(store.orders.data?.orders ?? []).flatMap((order) => [
			{ order, leg: false },
			...order.legs.map((leg) => ({ order: leg, leg: true }))
		])
	);

	function size(order: Order): string {
		if (order.notional !== null && order.qty === null) return money(order.notional);
		return order.qty === null ? DASH : quantity(order.qty);
	}

	function price(order: Order): string {
		const parts = [];
		if (order.limit_price !== null) parts.push(`limit ${money(order.limit_price, true)}`);
		if (order.stop_price !== null) parts.push(`stop ${money(order.stop_price, true)}`);
		if (order.trail_price !== null) parts.push(`trail ${money(order.trail_price, true)}`);
		if (order.trail_percent !== null) parts.push(`trail ${quantity(order.trail_percent)}%`);
		return parts.length > 0 ? parts.join(' · ') : 'market';
	}

	function filled(order: Order): string {
		if (!order.filled_qty) return DASH;
		return `${quantity(order.filled_qty)}${order.filled_avg_price !== null ? ` @ ${money(order.filled_avg_price, true)}` : ''}`;
	}

	// --- replacing an order -------------------------------------------------------------------------
	let replacing = $state<string | null>(null);
	let changes = $state({ qty: '', limit_price: '', stop_price: '', trail: '' });
	let replaceError = $state<string | null>(null);

	function startReplace(order: Order) {
		replacing = order.id;
		replaceError = null;
		changes = {
			qty: order.qty === null ? '' : String(order.qty),
			limit_price: order.limit_price === null ? '' : String(order.limit_price),
			stop_price: order.stop_price === null ? '' : String(order.stop_price),
			trail: String(order.trail_price ?? order.trail_percent ?? '')
		};
	}

	async function replace(order: Order) {
		const was = {
			qty: order.qty,
			limit_price: order.limit_price,
			stop_price: order.stop_price,
			trail: order.trail_price ?? order.trail_percent
		};
		const sent: Record<string, string> = {};
		for (const [name, value] of Object.entries(changes)) {
			const text = value.trim();
			const before = was[name as keyof typeof was];
			if (text !== '' && Number(text) !== before) sent[name] = text;
		}
		if (Object.keys(sent).length === 0) {
			replaceError = 'Change at least one value first.';
			return;
		}
		const result = await store.replaceOrder(order.id as string, sent);
		if (result.ok) replacing = null;
		else replaceError = result.message;
	}

	const canReplace = (order: Order) =>
		order.cancelable === true && order.notional === null && order.order_class !== 'mleg';
</script>

<SectionCard
	id="orders"
	title="Orders"
	description="Orders are listed newest first. Replacing an order sends it again with new values; cancelling sends a cancel request, and the status here shows what Alpaca did with it."
>
	{#snippet actions()}
		<ToggleGroup.Root
			type="single"
			size="sm"
			value={store.orderFilter}
			onValueChange={(v) => v && store.setOrderFilter(v as 'open' | 'closed' | 'all')}
			aria-label="Which orders"
		>
			<ToggleGroup.Item value="open">Open</ToggleGroup.Item>
			<ToggleGroup.Item value="closed">Closed</ToggleGroup.Item>
			<ToggleGroup.Item value="all">All</ToggleGroup.Item>
		</ToggleGroup.Root>
		<ConfirmAction
			label="Cancel all open orders"
			confirmLabel="Cancel every open order"
			description="Every open order is sent a cancel request."
			realMoney={store.realMoney}
			variant="destructive"
			disabled={store.busy > 0}
			onconfirm={async () => void (await store.cancelAllOrders())}
		/>
	{/snippet}

	{#if store.orders.problem && !store.orders.data}
		<p class="type-body-sm text-coral-ink" role="alert">{store.orders.problem}</p>
	{:else if !store.orders.data}
		<Skeleton class="h-40 w-full rounded-lg" />
	{:else}
		{#if store.orders.stale}<p class="type-caption text-ink-muted" role="status">
				Could not refresh: {store.orders.problem} Showing the last read.
			</p>{/if}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div
			class="max-w-full overflow-x-auto rounded-lg"
			role="region"
			aria-label="Orders table"
			tabindex="0"
		>
			<table class="w-full border-collapse type-body-sm" data-testid="orders-table">
				<thead>
					<tr class="border-b border-hairline text-left text-ink-muted">
						{#each ['Symbol', 'Side', 'Type', 'Size', 'Price', 'Filled', 'Status', 'Submitted', ''] as heading (heading)}
							<th scope="col" class="px-3 py-2 font-medium whitespace-nowrap"
								>{heading || 'Actions'}</th
							>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each rows as { order, leg } (order.id)}
						<tr
							class="border-b border-hairline-soft align-top last:border-0"
							data-testid="order-row"
							data-status={order.status}
						>
							<td
								class="px-3 py-2 font-mono font-medium {leg ? 'pl-8 text-ink-muted' : ''}"
								title={order.client_order_id ?? undefined}>{leg ? '↳ ' : ''}{order.symbol}</td
							>
							<td class="px-3 py-2 {order.side === 'buy' ? 'text-success-ink' : 'text-coral-ink'}"
								>{words(order.side)}</td
							>
							<td class="px-3 py-2 whitespace-nowrap"
								>{words(
									order.type
								)}{#if order.order_class && order.order_class !== 'simple' && !leg}<span
										class="text-ink-muted"
									>
										· {order.order_class}</span
									>{/if}</td
							>
							<td class="px-3 py-2 tabular-nums">{size(order)}</td>
							<td class="px-3 py-2 whitespace-nowrap tabular-nums"
								>{price(order)}<span class="ml-1 text-ink-muted"
									>· {(order.time_in_force ?? '').toUpperCase()}</span
								></td
							>
							<td class="px-3 py-2 whitespace-nowrap tabular-nums">{filled(order)}</td>
							<td class="px-3 py-2"
								><Badge variant={statusTone(order.status)}>{words(order.status)}</Badge></td
							>
							<td class="px-3 py-2 whitespace-nowrap text-ink-muted tabular-nums"
								>{when(order.submitted_at ?? order.created_at)}</td
							>
							<td class="px-3 py-2">
								{#if !leg && order.cancelable}
									<div class="flex flex-wrap gap-2">
										{#if canReplace(order)}<Button
												type="button"
												variant="translucent"
												size="xs"
												onclick={() =>
													replacing === order.id ? (replacing = null) : startReplace(order)}
												>Replace</Button
											>{/if}
										<Button
											type="button"
											variant="translucent"
											size="xs"
											disabled={store.busy > 0}
											onclick={() => store.cancelOrder(order.id as string)}>Cancel</Button
										>
									</div>
								{/if}
							</td>
						</tr>
						{#if replacing === order.id}
							<tr class="border-b border-hairline-soft bg-canvas" data-testid="replace-row">
								<td colspan="9" class="px-3 py-3">
									<form
										class="flex flex-wrap items-end gap-3"
										aria-label="Replace the order"
										onsubmit={(e) => (e.preventDefault(), void replace(order))}
									>
										{#if order.qty !== null}<Field
												id="replace-qty"
												label="Quantity (whole shares)"
												class="w-36"
												><Input
													id="replace-qty"
													bind:value={changes.qty}
													inputmode="numeric"
												/></Field
											>{/if}
										{#if order.limit_price !== null}<Field
												id="replace-limit"
												label="Limit price"
												class="w-36"
												><Input
													id="replace-limit"
													bind:value={changes.limit_price}
													inputmode="decimal"
												/></Field
											>{/if}
										{#if order.stop_price !== null}<Field
												id="replace-stop"
												label="Stop price"
												class="w-36"
												><Input
													id="replace-stop"
													bind:value={changes.stop_price}
													inputmode="decimal"
												/></Field
											>{/if}
										{#if order.trail_price !== null || order.trail_percent !== null}<Field
												id="replace-trail"
												label={order.trail_price !== null ? 'Trail amount' : 'Trail percent'}
												class="w-36"
												><Input
													id="replace-trail"
													bind:value={changes.trail}
													inputmode="decimal"
												/></Field
											>{/if}
										<Button type="submit" size="sm" disabled={store.busy > 0}>Replace order</Button>
										<Button
											type="button"
											variant="ghost"
											size="sm"
											onclick={() => (replacing = null)}>Close</Button
										>
									</form>
									{#if replaceError}<p class="mt-2 type-caption text-coral-ink" role="alert">
											{replaceError}
										</p>{/if}
								</td>
							</tr>
						{/if}
					{:else}
						<tr
							><td colspan="9" class="px-3 py-8 text-center text-ink-muted" data-testid="no-orders"
								>No {store.orderFilter === 'all' ? '' : store.orderFilter} orders.</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</SectionCard>
