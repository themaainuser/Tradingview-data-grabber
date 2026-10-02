<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Input } from '$lib/components/ui/input';
	import type { Asset } from '$lib/api/trading';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import { kindOf } from '$lib/trading/order';

	interface Props {
		store: TradingStore;
		value: string;
		id: string;
		onchange: (symbol: string) => void;
		placeholder?: string;
	}

	let {
		store,
		value,
		id,
		onchange,
		placeholder = 'AAPL, BTC/USD or an option contract'
	}: Props = $props();

	let results = $state.raw<Asset[]>([]);
	let open = $state(false);
	let focused = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;
	let controller: AbortController | undefined;
	onDestroy(() => {
		clearTimeout(timer);
		controller?.abort();
	});

	function search(text: string) {
		clearTimeout(timer);
		controller?.abort();
		const query = text.trim();
		if (query.length === 0 || query.length > 40 || kindOf(query) === 'us_option') {
			results = [];
			return;
		}
		timer = setTimeout(async () => {
			controller = new AbortController();
			try {
				const [stocks, crypto] = await Promise.all([
					query.includes('/') ? null : store.searchAssets(query, 'us_equity', controller.signal),
					store.searchAssets(query, 'crypto', controller.signal)
				]);
				results = [...(stocks?.assets ?? []), ...(crypto?.assets.slice(0, 4) ?? [])];
				open = focused && results.length > 0;
			} catch {
				results = []; // a search that fails (or is superseded) just offers nothing; typing a symbol still works
			}
		}, 250);
	}

	function pick(asset: Asset) {
		if (asset.symbol) onchange(asset.symbol);
		open = false;
		results = [];
	}
</script>

<div class="relative grid gap-1">
	<Input
		{id}
		{value}
		{placeholder}
		autocomplete="off"
		spellcheck="false"
		class="font-mono uppercase"
		aria-autocomplete="list"
		aria-controls="{id}-results"
		aria-expanded={open}
		onfocus={() => (focused = true)}
		onblur={() => ((focused = false), (open = false))}
		oninput={(e) => {
			onchange(e.currentTarget.value);
			search(e.currentTarget.value);
		}}
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
	/>
	{#if open && results.length > 0}
		<!-- Keeps the input focused while an option is clicked, so the list does not close before the click lands. -->
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<ul
			onmousedown={(e) => e.preventDefault()}
			id="{id}-results"
			class="absolute top-full z-20 mt-1 grid max-h-72 w-full overflow-y-auto rounded-lg border border-hairline bg-surface-1 p-1 shadow-lg"
			aria-label="Matching symbols"
			data-testid="symbol-results"
		>
			{#each results as asset (asset.id ?? asset.symbol)}
				<li>
					<button
						type="button"
						class="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left hover:bg-surface-2 pointer-coarse:min-h-11"
						onclick={() => pick(asset)}
					>
						<span class="font-mono type-body-sm font-medium">{asset.symbol}</span>
						<span class="min-w-0 flex-1 truncate type-caption text-ink-muted">{asset.name}</span>
						<span class="type-micro text-ink-muted"
							>{asset.exchange}{asset.tradable === false ? ' · not tradable' : ''}</span
						>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
