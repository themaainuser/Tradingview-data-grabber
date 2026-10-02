<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { Position } from '$lib/api/trading';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { quantity } from '$lib/trading/format';
	import ConfirmAction from './ConfirmAction.svelte';

	let { store, position }: { store: TradingStore; position: Position } = $props();

	let how = $state<'all' | 'qty' | 'percentage'>('all');
	let amount = $state('');
	let problem = $state<string | null>(null);

	const held = $derived(Math.abs(position.qty ?? 0));
	const describe = $derived(
		how === 'all'
			? `Close the whole position: ${position.side === 'short' ? 'buy back' : 'sell'} ${quantity(held)} ${position.symbol} at market.`
			: how === 'qty'
				? `${position.side === 'short' ? 'Buy back' : 'Sell'} ${amount || '…'} of ${quantity(held)} ${position.symbol} at market.`
				: `Close ${amount || '…'}% of the position in ${position.symbol} at market.`
	);

	async function close(): Promise<boolean> {
		problem = null;
		const text = amount.trim();
		if (how !== 'all') {
			const number = Number(text);
			if (!/^\d*\.?\d+$/.test(text) || number <= 0)
				return refuse('Enter a number greater than zero.');
			if (how === 'percentage' && number > 100) return refuse('A percentage is at most 100.');
			if (how === 'qty' && number > held) return refuse(`You hold ${quantity(held)}.`);
		}
		const result = await store.closePosition(
			position.symbol as string,
			how === 'all' ? {} : { [how]: text }
		);
		return result.ok || refuse(result.message);
	}

	/** Shows why nothing was sent and keeps the confirmation open. */
	function refuse(message: string): false {
		problem = message;
		return false;
	}
</script>

<ConfirmAction
	label="Close…"
	confirmLabel="Close it"
	description={describe}
	realMoney={store.realMoney}
	variant="translucent"
	size="xs"
	disabled={store.busy > 0}
	onconfirm={close}
>
	<ToggleGroup.Root
		type="single"
		size="sm"
		value={how}
		onValueChange={(v) => v && ((how = v as typeof how), (amount = ''), (problem = null))}
		aria-label="How much to close"
	>
		<ToggleGroup.Item value="all">Whole position</ToggleGroup.Item>
		<ToggleGroup.Item value="qty">Quantity</ToggleGroup.Item>
		<ToggleGroup.Item value="percentage">Percent</ToggleGroup.Item>
	</ToggleGroup.Root>
	{#if how !== 'all'}
		<Input
			bind:value={amount}
			inputmode="decimal"
			aria-label={how === 'qty' ? 'Quantity to close' : 'Percent to close'}
			placeholder={how === 'qty' ? `up to ${quantity(held)}` : '1 to 100'}
			class="w-40"
		/>
	{/if}
	{#if problem}<p class="type-caption text-coral-ink" role="alert">{problem}</p>{/if}
</ConfirmAction>
