<script lang="ts">
	import Database from '@lucide/svelte/icons/database';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import CandlestickChart from '@lucide/svelte/icons/chart-candlestick';
	import X from '@lucide/svelte/icons/x';
	import { MediaQuery } from 'svelte/reactivity';
	import { resolve } from '$app/paths';
	import { buttonVariants, Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import SpotlightCard from '$lib/components/app/SpotlightCard.svelte';
	import VirtualList from '$lib/components/app/VirtualList.svelte';
	import { formatTime } from '$lib/charts/scale';
	import { formatBytes, formatValue } from '$lib/format';
	import { getApp } from '$lib/state/app.svelte';
	import { cn } from '$lib/utils';

	const { datasets } = getApp();

	const TEMPLATE = 'minmax(10rem,1.6fr) 5rem 6.5rem 14rem 6rem 8rem 1fr';

	// Below the 810px tablet breakpoint rows stack instead of scrolling sideways (DESIGN.md, Collapsing Strategy).
	const narrow = new MediaQuery('max-width: 809px');

	const explore = (id: string) => resolve('/explorer/[[dataset]]', { dataset: id });

	// Figures for the summary card come straight from the backend listing; nothing is estimated.
	const summary = $derived({
		captures: datasets.usable.length,
		bars: datasets.usable.reduce((sum, d) => sum + d.rows, 0),
		symbols: new Set(datasets.usable.map((d) => d.symbol)).size
	});
</script>

<div class="grid gap-[96px]">
	<section class="grid items-end gap-[30px] md:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
		<div class="grid gap-5">
			<p class="type-caption text-ink-muted">Research workspace</p>
			<h1 class="type-display-xl">Datasets</h1>
			<p class="max-w-xl type-body-lg text-ink-muted">
				Captures found in the backend data directory, plus files you import in this tab. Open one to
				chart it, filter it and measure what happened next.
			</p>
			<div class="flex flex-wrap gap-2">
				<Button
					variant="secondary"
					disabled={datasets.status === 'loading'}
					onclick={() => datasets.load()}
				>
					<RefreshCw
						class={datasets.status === 'loading' ? 'animate-spin' : ''}
						aria-hidden="true"
					/> Refresh
				</Button>
			</div>
		</div>

		{#if datasets.status === 'ready' && summary.captures > 0}
			<SpotlightCard tone="violet" class="grid gap-5">
				<p class="type-caption">On this backend</p>
				<p class="type-display-lg tabular-nums" data-testid="summary-bars">
					{formatValue(summary.bars, 'int')}
				</p>
				<p class="type-subhead">
					bars across {summary.captures} capture{summary.captures === 1 ? '' : 's'}
					and {summary.symbols} symbol{summary.symbols === 1 ? '' : 's'}
				</p>
			</SpotlightCard>
		{/if}
	</section>

	{#if datasets.status === 'error' && datasets.error}
		<ErrorPanel
			error={datasets.error}
			title="Could not load datasets"
			onretry={() => datasets.load()}
		/>
	{:else if datasets.status === 'loading' && datasets.items.length === 0}
		<div class="grid gap-2" aria-busy="true" aria-label="Loading datasets">
			{#each [0, 1, 2] as n (n)}<Skeleton class="h-11 w-full" />{/each}
		</div>
	{:else if datasets.isEmpty}
		<EmptyState
			tone="violet"
			icon={Database}
			title="No datasets yet"
			description="The backend data directory has no OHLCV captures. Capture bars with the command below, or use Import CSV in the top bar to explore a file locally."
		>
			<code class="rounded-md bg-spotlight-well px-3 py-2 font-mono type-caption"
				>tvdata bars -n EXCHANGE:SYMBOL -t 5 -o data --once</code
			>
		</EmptyState>
	{/if}

	{#if datasets.items.length > 0}
		<section aria-labelledby="backend-heading" class="grid gap-[15px]">
			<h2 id="backend-heading" class="flex items-baseline gap-3 type-display-md">
				Backend captures
				<span class="type-body text-ink-muted tabular-nums">{datasets.items.length}</span>
			</h2>
			<VirtualList
				count={datasets.items.length}
				itemHeight={narrow.current ? 124 : 52}
				label="Backend datasets"
				minWidth={narrow.current ? undefined : 860}
				class="max-h-[30rem] bg-canvas"
				key={(i) => datasets.items[i].id}
			>
				{#snippet header()}
					{#if !narrow.current}
						<div
							class="grid items-center gap-3 px-2 py-3 type-caption text-ink-muted"
							style:grid-template-columns={TEMPLATE}
						>
							<span role="columnheader">Symbol</span>
							<span role="columnheader">Timeframe</span>
							<span role="columnheader" class="text-right">Rows</span>
							<span role="columnheader">Range (UTC)</span>
							<span role="columnheader" class="text-right">Size</span>
							<span role="columnheader">Status</span>
							<span role="columnheader"><span class="sr-only">Actions</span></span>
						</div>
					{/if}
				{/snippet}
				{#snippet row(index)}
					{@const d = datasets.items[index]}
					{#if narrow.current}
						<div
							class="grid h-full content-center gap-2 px-1 type-body-sm tabular-nums"
							role="presentation"
						>
							<div class="flex items-center gap-2">
								<span role="cell" class="min-w-0 flex-1 truncate" title={d.path}>{d.symbol}</span>
								<span role="cell">
									{#if d.valid}<Badge variant="success">Ready</Badge>{/if}
								</span>
							</div>
							<div role="cell" class="truncate type-caption text-ink-muted">
								{#if d.valid}
									{d.timeframe ? `${d.timeframe} · ` : ''}{formatValue(d.rows, 'int')} rows · {formatBytes(
										d.size_bytes
									)}
								{:else}
									<span class="text-coral-ink">{d.error ?? 'Invalid file'}</span>
								{/if}
							</div>
							<div class="flex items-center gap-2">
								<div role="cell" class="min-w-0 flex-1 truncate type-caption text-ink-muted">
									{d.start !== null && d.end !== null
										? `${formatTime(d.start, false)} – ${formatTime(d.end, false)}`
										: '—'}
								</div>
								{#if d.valid}
									<a
										href={explore(d.id)}
										class={cn(buttonVariants({ variant: 'secondary', size: 'sm' }))}
									>
										<CandlestickChart aria-hidden="true" /> Explore
									</a>
								{/if}
							</div>
						</div>
					{:else}
						<div
							class="grid h-full items-center gap-3 px-2 type-body-sm tabular-nums"
							style:grid-template-columns={TEMPLATE}
							role="presentation"
						>
							<span role="cell" class="truncate" title={d.path}>{d.symbol}</span>
							<span role="cell" class="text-ink-muted">{d.timeframe ?? '—'}</span>
							<span role="cell" class="text-right">{formatValue(d.rows, 'int')}</span>
							<span role="cell" class="whitespace-nowrap text-ink-muted">
								{d.start !== null && d.end !== null
									? `${formatTime(d.start, false)} – ${formatTime(d.end, false)}`
									: '—'}
							</span>
							<span role="cell" class="text-right text-ink-muted">{formatBytes(d.size_bytes)}</span>
							<span role="cell">
								{#if d.valid}
									<Badge variant="success">Ready</Badge>
								{:else}
									<span class="block truncate type-caption text-coral-ink" title={d.error ?? ''}
										>{d.error ?? 'Invalid file'}</span
									>
								{/if}
							</span>
							<span role="cell" class="flex justify-end">
								{#if d.valid}
									<a
										href={explore(d.id)}
										class={cn(buttonVariants({ variant: 'secondary', size: 'sm' }))}
									>
										<CandlestickChart aria-hidden="true" /> Explore
									</a>
								{/if}
							</span>
						</div>
					{/if}
				{/snippet}
			</VirtualList>
		</section>
	{/if}

	{#if datasets.local.length > 0}
		<section aria-labelledby="local-heading" class="grid gap-[15px]">
			<div class="grid gap-1">
				<h2 id="local-heading" class="flex items-baseline gap-3 type-display-md">
					Imported in this tab
					<span class="type-body text-ink-muted tabular-nums">{datasets.local.length}</span>
				</h2>
				<p class="max-w-xl type-body text-pretty text-ink-muted">
					Held in memory only. Reloading the page discards them, and they cannot be used for backend
					research runs.
				</p>
			</div>
			<ul class="grid grid-cols-[minmax(0,1fr)] gap-2">
				{#each datasets.local as bars (bars.id)}
					<li
						class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-surface-1 px-5 py-[15px] type-body-sm tabular-nums"
					>
						<span>{bars.symbol}</span>
						<span class="text-ink-muted">{bars.length.toLocaleString('en-US')} bars</span>
						{#if bars.droppedRows > 0}<span class="type-caption text-ink-muted"
								>{bars.droppedRows} invalid rows dropped</span
							>{/if}
						{#if bars.duplicateRows > 0}<span class="type-caption text-ink-muted"
								>{bars.duplicateRows} duplicates collapsed</span
							>{/if}
						<span class="ml-auto flex items-center gap-1">
							<a
								href={explore(bars.id)}
								class={cn(buttonVariants({ variant: 'translucent', size: 'sm' }))}
							>
								<CandlestickChart aria-hidden="true" /> Explore
							</a>
							<Button
								variant="ghost"
								size="icon-sm"
								aria-label="Remove {bars.symbol}"
								onclick={() => datasets.removeLocal(bars.id)}
							>
								<X aria-hidden="true" />
							</Button>
						</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}
</div>
