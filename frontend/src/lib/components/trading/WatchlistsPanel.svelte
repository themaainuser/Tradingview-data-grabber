<script lang="ts">
	import { onMount } from 'svelte';
	import X from '@lucide/svelte/icons/x';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import ConfirmAction from './ConfirmAction.svelte';
	import Field from './Field.svelte';
	import SymbolPicker from './SymbolPicker.svelte';

	let {
		store,
		ontrade
	}: { store: TradingStore; ontrade: (symbol: string, side: 'buy' | 'sell') => void } = $props();

	onMount(() => {
		void store.loadWatchlists();
	});

	let selectedId = $state<string | null>(null);
	let newName = $state('');
	let renameTo = $state('');
	let symbol = $state('');

	const lists = $derived(store.watchlists.data?.watchlists ?? []);
	const selected = $derived(lists.find((w) => w.id === selectedId) ?? lists[0] ?? null);
	// The list from Alpaca leaves each watchlist's assets out, so the open one is read in full.
	let detail = $state.raw<import('$lib/api/trading').Watchlist | null>(null);
	$effect(() => {
		const id = selected?.id ?? null;
		detail = null;
		if (!id || !store.env) return;
		const env = store.env;
		const watcher = store.watchlists.envelope;
		void (async () => {
			const full = await store.readWatchlist(id);
			if (store.env === env && watcher === store.watchlists.envelope) detail = full;
		})();
	});

	async function create() {
		const name = newName.trim();
		if (!name) return;
		const result = await store.createWatchlist(name, []);
		if (result.ok) {
			newName = '';
			selectedId = result.envelope?.data?.id ?? null;
		}
	}

	async function add() {
		const wanted = symbol.trim().toUpperCase();
		if (!selected?.id || !wanted) return;
		const result = await store.addToWatchlist(selected.id, wanted);
		if (result.ok) {
			symbol = '';
			detail = result.envelope?.data ?? detail;
		}
	}

	async function remove(name: string) {
		if (!selected?.id) return;
		const result = await store.removeFromWatchlist(selected.id, name);
		if (result.ok) detail = result.envelope?.data ?? detail;
	}
</script>

<SectionCard
	id="watchlists"
	title="Watchlists"
	description="Symbols you follow. They are kept by Alpaca, so they are the same in its own apps."
>
	{#if store.watchlists.problem && !store.watchlists.data}
		<p class="type-body-sm text-coral-ink" role="alert">{store.watchlists.problem}</p>
	{:else if !store.watchlists.data}
		<Skeleton class="h-40 w-full rounded-lg" />
	{:else}
		<div class="grid min-w-0 gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
			<div class="grid content-start gap-3">
				<ul class="grid gap-1" aria-label="Watchlists" data-testid="watchlist-list">
					{#each lists as w (w.id)}
						<li>
							<button
								type="button"
								class="w-full rounded-lg px-3 py-2 text-left type-body-sm hover:bg-surface-2 aria-[current=true]:bg-surface-2 pointer-coarse:min-h-11"
								aria-current={selected?.id === w.id ? 'true' : undefined}
								onclick={() => ((selectedId = w.id), (renameTo = w.name ?? ''))}>{w.name}</button
							>
						</li>
					{:else}
						<li class="type-caption text-ink-muted" data-testid="no-watchlists">
							No watchlists yet.
						</li>
					{/each}
				</ul>
				<form
					class="grid gap-2"
					onsubmit={(e) => (e.preventDefault(), void create())}
					aria-label="New watchlist"
				>
					<Field id="watchlist-new" label="New watchlist"
						><Input
							id="watchlist-new"
							bind:value={newName}
							placeholder="Name"
							maxlength={64}
						/></Field
					>
					<Button
						type="submit"
						variant="translucent"
						size="sm"
						class="w-fit"
						disabled={!newName.trim() || store.busy > 0}>Create</Button
					>
				</form>
			</div>

			{#if selected}
				<div class="grid min-w-0 content-start gap-4" data-testid="watchlist-detail">
					<div class="flex flex-wrap items-end gap-3">
						<Field id="watchlist-rename" label="Name" class="w-56"
							><Input id="watchlist-rename" bind:value={renameTo} maxlength={64} /></Field
						>
						<Button
							type="button"
							variant="translucent"
							size="sm"
							disabled={!renameTo.trim() || renameTo.trim() === selected.name || store.busy > 0}
							onclick={() => selected.id && store.renameWatchlist(selected.id, renameTo.trim())}
							>Rename</Button
						>
						<ConfirmAction
							label="Delete"
							confirmLabel="Delete the watchlist"
							description="Deletes the watchlist {selected.name} for good."
							realMoney={false}
							variant="destructive"
							onconfirm={async () =>
								void (selected.id && (await store.deleteWatchlist(selected.id)))}
						/>
					</div>
					<form
						class="flex flex-wrap items-end gap-3"
						onsubmit={(e) => (e.preventDefault(), void add())}
						aria-label="Add a symbol"
					>
						<Field id="watchlist-symbol" label="Add a symbol" class="w-64"
							><SymbolPicker
								{store}
								id="watchlist-symbol"
								value={symbol}
								onchange={(s) => (symbol = s)}
								placeholder="AAPL"
							/></Field
						>
						<Button type="submit" size="sm" disabled={!symbol.trim() || store.busy > 0}>Add</Button>
					</form>
					{#if !detail}
						<Skeleton class="h-20 w-full rounded-lg" />
					{:else}
						<ul
							class="grid gap-1"
							aria-label="Symbols in {selected.name}"
							data-testid="watchlist-assets"
						>
							{#each detail.assets as asset (asset.id ?? asset.symbol)}
								<li class="flex flex-wrap items-center gap-3 rounded-lg bg-canvas px-3 py-2">
									<span class="font-mono type-body-sm font-medium">{asset.symbol}</span>
									<span class="min-w-0 flex-1 truncate type-caption text-ink-muted"
										>{asset.name}</span
									>
									<Button
										type="button"
										variant="translucent"
										size="xs"
										onclick={() => ontrade(asset.symbol as string, 'buy')}>Trade</Button
									>
									<Button
										type="button"
										variant="ghost"
										size="icon-sm"
										aria-label="Remove {asset.symbol}"
										disabled={store.busy > 0}
										onclick={() => remove(asset.symbol as string)}><X aria-hidden="true" /></Button
									>
								</li>
							{:else}
								<li class="type-caption text-ink-muted" data-testid="empty-watchlist">
									No symbols in this watchlist yet.
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</SectionCard>
