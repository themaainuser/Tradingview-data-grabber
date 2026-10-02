<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { DASH, money, quantity } from '$lib/trading/format';
	import Field from './Field.svelte';

	interface Props {
		store: TradingStore;
		/** The underlying to start from, usually the symbol in the ticket. */
		underlying?: string;
		multiLeg: boolean;
		onuse: (symbol: string, as: 'single' | 'leg') => void;
	}

	let { store, underlying = '', multiLeg, onuse }: Props = $props();

	let symbol = $state('');
	let type = $state<'any' | 'call' | 'put'>('any');
	let from = $state('');
	let to = $state('');
	let strikeFrom = $state('');
	let strikeTo = $state('');
	$effect(() => {
		if (!symbol && underlying && !/\d{6}[CP]\d{8}$/.test(underlying) && !underlying.includes('/'))
			symbol = underlying.toUpperCase();
	});

	function search(event?: SubmitEvent) {
		event?.preventDefault();
		const wanted = symbol.trim().toUpperCase();
		if (!wanted) return;
		void store.loadContracts({
			underlying_symbols: wanted,
			...(type === 'any' ? {} : { type }),
			...(from ? { expiration_date_gte: from } : {}),
			...(to ? { expiration_date_lte: to } : {}),
			...(strikeFrom ? { strike_price_gte: strikeFrom } : {}),
			...(strikeTo ? { strike_price_lte: strikeTo } : {})
		});
	}

	const contracts = $derived(store.contracts.data?.contracts ?? []);
</script>

<SectionCard
	id="contracts"
	title="Find an option contract"
	description="Alpaca lists the contracts that exist. By default it returns only those expiring before the coming weekend, so widen the dates to see more."
>
	<form
		class="grid grid-cols-2 items-end gap-3 md:grid-cols-6"
		onsubmit={search}
		aria-label="Contract search"
	>
		<Field id="contracts-underlying" label="Underlying" class="col-span-2 md:col-span-1"
			><Input
				id="contracts-underlying"
				bind:value={symbol}
				placeholder="AAPL"
				class="font-mono uppercase"
			/></Field
		>
		<Field id="contracts-type" label="Type">
			<Select.Root type="single" value={type} onValueChange={(v) => v && (type = v as typeof type)}>
				<Select.Trigger id="contracts-type" class="w-full"
					>{type === 'any' ? 'Calls and puts' : type === 'call' ? 'Calls' : 'Puts'}</Select.Trigger
				>
				<Select.Content
					><Select.Item value="any" label="Calls and puts">Calls and puts</Select.Item><Select.Item
						value="call"
						label="Calls">Calls</Select.Item
					><Select.Item value="put" label="Puts">Puts</Select.Item></Select.Content
				>
			</Select.Root>
		</Field>
		<Field id="contracts-from" label="Expires from"
			><Input id="contracts-from" type="date" bind:value={from} /></Field
		>
		<Field id="contracts-to" label="Expires to"
			><Input id="contracts-to" type="date" bind:value={to} /></Field
		>
		<Field id="contracts-strike-from" label="Strike from"
			><Input id="contracts-strike-from" bind:value={strikeFrom} inputmode="decimal" /></Field
		>
		<Field id="contracts-strike-to" label="Strike to"
			><Input id="contracts-strike-to" bind:value={strikeTo} inputmode="decimal" /></Field
		>
		<Button
			type="submit"
			variant="translucent"
			size="sm"
			class="col-span-2 w-fit md:col-span-6"
			disabled={!symbol.trim() || !store.usable}>Search contracts</Button
		>
	</form>
	{#if store.contracts.problem && !store.contracts.data}
		<p class="type-body-sm text-coral-ink" role="alert">{store.contracts.problem}</p>
	{:else if store.contracts.data}
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div
			class="max-w-full overflow-x-auto rounded-lg"
			role="region"
			aria-label="Contracts table"
			tabindex="0"
		>
			<table class="w-full border-collapse type-body-sm" data-testid="contracts-table">
				<thead>
					<tr class="border-b border-hairline text-left text-ink-muted">
						{#each ['Contract', 'Type', 'Strike', 'Expires', 'Open interest', 'Last close', ''] as heading (heading)}
							<th scope="col" class="px-3 py-2 font-medium whitespace-nowrap">{heading || 'Use'}</th
							>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each contracts as c (c.id ?? c.symbol)}
						<tr class="border-b border-hairline-soft last:border-0" data-testid="contract-row">
							<td class="px-3 py-2 font-mono">{c.symbol}</td>
							<td class="px-3 py-2"
								>{c.type === 'call' ? 'Call' : c.type === 'put' ? 'Put' : DASH}</td
							>
							<td class="px-3 py-2 tabular-nums">{money(c.strike_price, true)}</td>
							<td class="px-3 py-2 whitespace-nowrap tabular-nums">{c.expiration_date ?? DASH}</td>
							<td class="px-3 py-2 tabular-nums">{quantity(c.open_interest)}</td>
							<td class="px-3 py-2 tabular-nums">{money(c.close_price, true)}</td>
							<td class="px-3 py-2">
								<div class="flex gap-2">
									{#if multiLeg}<Button
											type="button"
											variant="translucent"
											size="xs"
											onclick={() => onuse(c.symbol as string, 'leg')}>Add as leg</Button
										>{/if}
									<Button
										type="button"
										variant="translucent"
										size="xs"
										onclick={() => onuse(c.symbol as string, 'single')}>Trade</Button
									>
								</div>
							</td>
						</tr>
					{:else}
						<tr
							><td
								colspan="7"
								class="px-3 py-6 text-center text-ink-muted"
								data-testid="no-contracts">No contracts match. Try a wider range of dates.</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>
		{#if store.contracts.data.next_page_token}<p class="type-caption text-ink-muted">
				More contracts exist than are listed; narrow the search to see them.
			</p>{/if}
	{/if}
</SectionCard>
