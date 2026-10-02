<script lang="ts">
	import { onMount } from 'svelte';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import ShieldAlert from '@lucide/svelte/icons/shield-alert';
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import { Button } from '$lib/components/ui/button';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { timeUntil } from '$lib/trading/format';

	let { store, onselect }: { store: TradingStore; onselect: (env: string) => void } = $props();

	// The clock line says "closes in 2h 05m", so it has to keep moving.
	let now = $state(Date.now());
	onMount(() => {
		const timer = setInterval(() => (now = Date.now()), 30_000);
		return () => clearInterval(timer);
	});

	const environment = $derived(store.environment);
	const clock = $derived(store.clock.data);
	const account = $derived(store.account.data);
</script>

<div class="grid gap-3">
	<div
		class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-4 py-3 {store.realMoney
			? 'bg-coral-ink/15'
			: 'bg-success-ink/10'}"
		role="status"
		data-testid="environment-banner"
		data-real-money={store.realMoney ? 'true' : 'false'}
	>
		{#if store.realMoney}
			<ShieldAlert class="size-5 shrink-0 text-coral-ink" aria-hidden="true" />
			<strong class="type-body-sm font-semibold text-coral-ink">LIVE trading · real money</strong>
		{:else}
			<ShieldCheck class="size-5 shrink-0 text-success-ink" aria-hidden="true" />
			<strong class="type-body-sm font-semibold text-success-ink"
				>Paper trading · simulated money</strong
			>
		{/if}
		{#if account?.account_number}<span
				class="type-caption text-ink-muted"
				data-testid="account-number">Account {account.account_number}</span
			>{/if}
		{#if clock}
			<span class="type-caption text-ink-muted tabular-nums" data-testid="market-clock">
				{#if clock.is_open}
					<span class="text-success-ink">Market open</span> · closes in {timeUntil(
						clock.next_close,
						now
					)}
				{:else}
					Market closed · opens in {timeUntil(clock.next_open, now)}
				{/if}
			</span>
		{/if}
		<Button
			type="button"
			variant="ghost"
			size="xs"
			class="ml-auto"
			disabled={!store.usable || store.refreshing}
			onclick={() => store.refresh()}
		>
			<RefreshCw class={store.refreshing ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
		</Button>
	</div>

	<ToggleGroup.Root
		type="single"
		size="sm"
		value={store.env ?? ''}
		onValueChange={(v) => v && onselect(v)}
		aria-label="Trading environment"
		class="flex-wrap"
	>
		{#each store.environments as e (e.id)}
			<ToggleGroup.Item
				value={e.id}
				class={e.real_money ? 'data-[state=on]:text-coral-ink' : ''}
				title={e.enabled ? e.label : (e.note ?? e.label)}
			>
				{e.label}{#if !e.enabled}<span class="ml-1 text-ink-muted">· off</span
					>{:else if !e.configured}<span class="ml-1 text-ink-muted">· no keys</span>{/if}
			</ToggleGroup.Item>
		{/each}
	</ToggleGroup.Root>
	{#if environment && !environment.enabled && environment.note}
		<p class="max-w-[72ch] type-caption text-ink-muted">{environment.note}</p>
	{/if}
</div>
