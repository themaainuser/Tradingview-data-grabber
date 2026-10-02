<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ArrowLeftRight from '@lucide/svelte/icons/arrow-left-right';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import AccountPanel from '$lib/components/trading/AccountPanel.svelte';
	import ActivityPanel from '$lib/components/trading/ActivityPanel.svelte';
	import ContractBrowser from '$lib/components/trading/ContractBrowser.svelte';
	import EnvironmentBar from '$lib/components/trading/EnvironmentBar.svelte';
	import OrderTicket from '$lib/components/trading/OrderTicket.svelte';
	import OrdersPanel from '$lib/components/trading/OrdersPanel.svelte';
	import PositionsPanel from '$lib/components/trading/PositionsPanel.svelte';
	import SettingsPanel from '$lib/components/trading/SettingsPanel.svelte';
	import SetupPanel from '$lib/components/trading/SetupPanel.svelte';
	import WatchlistsPanel from '$lib/components/trading/WatchlistsPanel.svelte';
	import { getApp } from '$lib/state/app.svelte';
	import { VIEWS, isView, type ViewName } from '$lib/state/trading.svelte';
	import { emptyDraft, emptyLeg, normalize, type OrderDraft } from '$lib/trading/order';

	const { trading: store } = getApp();
	const ROUTE = '/trading/[[env]]/[[view]]' as const;

	const envParam = $derived(page.params.env ?? null);
	const viewParam = $derived(page.params.view ?? null);
	const view = $derived<ViewName>(isView(viewParam) ? viewParam : 'overview');

	// The draft lives here, not in the ticket, so a symbol chosen on another tab is waiting when you open Trade.
	let draft = $state<OrderDraft>(emptyDraft());

	function go(env: string, next: ViewName | null, replace = false) {
		const path =
			next && next !== 'overview' ? resolve(ROUTE, { env, view: next }) : resolve(ROUTE, { env });
		void goto(path, { replaceState: replace, keepFocus: true, noScroll: true });
	}

	onMount(() => {
		void store.loadEnvironments();
		return store.startRefreshing();
	});

	// The address chooses the environment. With no environment in it, paper is the one that opens: never live.
	$effect(() => {
		const known = store.environmentsStatus === 'ready' ? store.environments : null;
		const wanted = envParam;
		if (!known) return;
		untrack(() => {
			if (!wanted) {
				go(known.some((e) => e.id === 'paper') ? 'paper' : (known[0]?.id ?? 'paper'), null, true);
				return;
			}
			store.select(known.some((e) => e.id === wanted) ? wanted : null);
		});
	});

	// What the page needs as soon as the environment is usable.
	$effect(() => {
		const ready = store.usable && store.env;
		if (!ready) return;
		untrack(() => {
			void store.loadAccount();
			void store.loadClock();
			void store.loadPositions();
			void store.loadOrders();
		});
	});

	const unknownEnvironment = $derived(
		store.environmentsStatus === 'ready' &&
			envParam !== null &&
			!store.environments.some((e) => e.id === envParam)
	);

	/** From a position or a watchlist: open the ticket with this symbol (and side) ready, and place nothing. */
	function trade(symbol: string, side: 'buy' | 'sell' = 'buy') {
		draft = normalize({ ...emptyDraft(symbol), side });
		if (store.env) go(store.env, 'trade');
	}

	function useContract(symbol: string, as: 'single' | 'leg') {
		if (as === 'single') return trade(symbol);
		const legs = [...draft.legs];
		const free = legs.findIndex((leg) => leg.symbol.trim() === '');
		if (free >= 0) legs[free] = { ...legs[free], symbol };
		else if (legs.length < 4) legs.push({ ...emptyLeg(), symbol });
		draft = { ...draft, multiLeg: true, legs };
	}
</script>

<svelte:head>
	<title>Trading · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-8">
	<header class="grid max-w-[860px] gap-4">
		<p class="type-caption text-ink-muted">Alpaca</p>
		<h1 class="type-display-lg">Trading</h1>
		<p class="max-w-[62ch] type-body-lg text-ink-muted">
			Place and manage orders on your Alpaca account, with the same screen for paper and live
			trading. Paper is the default; the page always says which account you are looking at, and an
			order is only sent after you review it.
		</p>
	</header>

	{#if store.environmentsStatus === 'error' && store.environmentsError}
		<ErrorPanel
			error={store.environmentsError}
			title="Could not load the trading environments"
			onretry={() => store.loadEnvironments()}
		/>
	{:else if store.environmentsStatus !== 'ready'}
		<div class="grid gap-4" role="status" aria-live="polite">
			<span class="sr-only">Loading…</span><Skeleton class="h-14 w-full rounded-xl" /><Skeleton
				class="h-96 w-full rounded-xl"
			/>
		</div>
	{:else if unknownEnvironment}
		<EmptyState
			icon={ArrowLeftRight}
			title="Environment not found"
			description="Choose paper or live from the address, or open the trading page without one."
		>
			<Button variant="translucent" size="sm" onclick={() => go('paper', null)}
				>Open paper trading</Button
			>
		</EmptyState>
	{:else if store.env}
		<EnvironmentBar {store} onselect={(env) => go(env, view)} />

		{#if store.notice}
			<Alert.Root
				variant={store.notice.tone === 'error' ? 'destructive' : 'default'}
				role={store.notice.tone === 'error' ? 'alert' : 'status'}
				data-testid="notice"
			>
				<Alert.Description>
					<div class="flex flex-wrap items-center gap-3">
						<p class="min-w-0 flex-1 text-pretty">{store.notice.text}</p>
						<Button type="button" variant="ghost" size="xs" onclick={() => store.dismissNotice()}
							>Dismiss</Button
						>
					</div>
				</Alert.Description>
			</Alert.Root>
		{/if}

		{#if store.environment && !store.usable}
			<SetupPanel environment={store.environment} />
		{:else}
			<nav
				aria-label="Trading sections"
				class="flex w-fit max-w-full flex-wrap gap-1 rounded-full bg-surface-1 p-1"
			>
				{#each VIEWS as v (v.id)}
					<a
						href={resolve(
							ROUTE,
							v.id === 'overview' ? { env: store.env } : { env: store.env, view: v.id }
						)}
						aria-current={view === v.id ? 'page' : undefined}
						class="rounded-full px-4 py-2 type-button text-ink-muted transition-colors duration-150 hover:text-ink aria-[current=page]:bg-surface-2 aria-[current=page]:text-ink pointer-coarse:min-h-11"
					>
						{v.label}
					</a>
				{/each}
			</nav>

			{#if view === 'overview'}
				<AccountPanel {store} ongo={(next) => store.env && go(store.env, next)} />
				<PositionsPanel {store} ontrade={trade} />
			{:else if view === 'trade'}
				<div class="grid min-w-0 gap-6">
					<OrderTicket {store} bind:draft />
					<ContractBrowser
						{store}
						underlying={draft.symbol}
						multiLeg={draft.multiLeg}
						onuse={useContract}
					/>
				</div>
			{:else if view === 'orders'}
				<OrdersPanel {store} />
			{:else if view === 'positions'}
				<PositionsPanel {store} ontrade={trade} />
			{:else if view === 'watchlists'}
				<WatchlistsPanel {store} ontrade={trade} />
			{:else if view === 'activity'}
				<ActivityPanel {store} />
			{:else if view === 'settings'}
				<SettingsPanel {store} />
			{/if}
		{/if}
	{/if}
</div>
