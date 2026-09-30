<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import CandlestickChart from '@lucide/svelte/icons/chart-candlestick';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import * as Card from '$lib/components/ui/card';
	import * as Select from '$lib/components/ui/select';
	import CandleChart from '$lib/components/app/CandleChart.svelte';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import FilterBuilder from '$lib/components/filters/FilterBuilder.svelte';
	import IndicatorPanel from '$lib/components/explorer/IndicatorPanel.svelte';
	import MatchesTable from '$lib/components/explorer/MatchesTable.svelte';
	import EventStudyPanel from '$lib/components/explorer/EventStudyPanel.svelte';
	import { createExplorerCatalog } from '$lib/explorer/catalog';
	import { fieldLabel } from '$lib/explorer/fields';
	import { isIntraday, formatTime } from '$lib/charts/scale';
	import { formatDuration, formatValue } from '$lib/format';
	import { getApp } from '$lib/state/app.svelte';
	import { ExplorerStore } from '$lib/state/explorer.svelte';

	const app = getApp();
	const { datasets, explorerFilters } = app;
	// Lives on AppState so an open dataset survives navigating away and back.
	const explorer = (app.explorer ??= new ExplorerStore(app.api));
	const catalog = createExplorerCatalog();

	const requested = $derived(page.params.dataset ?? null);

	// URL -> store: opening /explorer/<id> (a link, reload or shared URL) loads that dataset.
	$effect(() => {
		const id = requested;
		if (!id) return;
		untrack(() => {
			if (id.startsWith('local:')) {
				const local = datasets.findLocal(id);
				if (local) explorer.openLocal(local);
			} else {
				explorer.openBackend(id);
			}
		});
	});

	const bars = $derived(explorer.bars);
	const intraday = $derived(bars ? isIntraday(bars.columns.time) : false);
	const missingLocal = $derived(requested?.startsWith('local:') && !datasets.findLocal(requested));
	const selectedLabel = $derived(
		bars ? `${bars.symbol}${bars.timeframe ? ` · ${bars.timeframe}` : ''}` : 'Choose a dataset'
	);

	function choose(id: string) {
		goto(resolve('/explorer/[[dataset]]', { dataset: id }), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	const matchFields = $derived(
		explorer.source
			? explorer.referencedFields
					.filter((key) => key !== 'close' && key !== 'volume')
					.flatMap((key) => {
						const values = explorer.source!.numeric(key);
						return values ? [{ key, label: fieldLabel(key), values }] : [];
					})
			: []
	);
</script>

<div class="grid gap-[30px]">
	<header class="flex flex-wrap items-end gap-5">
		<div class="grid gap-2">
			<h1 class="type-display-md">Explorer</h1>
			<p class="max-w-xl type-body text-pretty text-ink-muted">
				Overlay indicators, filter bars with compound conditions and measure what happened next.
			</p>
		</div>
		<div class="ml-auto">
			<Select.Root type="single" value={bars?.id ?? ''} onValueChange={choose}>
				<Select.Trigger class="w-64" aria-label="Dataset">{selectedLabel}</Select.Trigger>
				<Select.Content>
					{#if datasets.usable.length > 0}
						<Select.Group>
							<Select.GroupHeading>Backend captures</Select.GroupHeading>
							{#each datasets.usable as d (d.id)}
								<Select.Item value={d.id} label={d.symbol}>
									{d.symbol}{d.timeframe ? ` · ${d.timeframe}` : ''}
									<span class="ml-auto type-caption text-ink-muted tabular-nums"
										>{d.rows.toLocaleString('en-US')}</span
									>
								</Select.Item>
							{/each}
						</Select.Group>
					{/if}
					{#if datasets.local.length > 0}
						<Select.Group>
							<Select.GroupHeading>Imported (this tab)</Select.GroupHeading>
							{#each datasets.local as b (b.id)}
								<Select.Item value={b.id} label={b.symbol}>{b.symbol}</Select.Item>
							{/each}
						</Select.Group>
					{/if}
					{#if datasets.usable.length === 0 && datasets.local.length === 0}
						<p class="px-3 py-3 type-body text-ink-muted">No datasets available.</p>
					{/if}
				</Select.Content>
			</Select.Root>
		</div>
	</header>

	{#if explorer.status === 'error' && explorer.error}
		<ErrorPanel
			error={explorer.error}
			title="Could not load bars"
			onretry={() => requested && explorer.openBackend(requested)}
		/>
	{:else if explorer.status === 'loading'}
		<div class="grid gap-3" aria-busy="true" aria-label="Loading bars">
			<Skeleton class="h-6 w-1/2" />
			<Skeleton class="h-96 w-full" />
		</div>
	{:else if missingLocal}
		<EmptyState
			icon={CandlestickChart}
			title="That imported file is no longer available"
			description="Imported CSVs live in memory and are dropped when the page reloads. Import the file again to continue."
		/>
	{:else if !bars}
		<EmptyState
			tone="orange"
			icon={CandlestickChart}
			title="No dataset open"
			description={datasets.usable.length > 0 || datasets.local.length > 0
				? 'Pick a dataset above to load its bars.'
				: 'Nothing to explore yet. Capture bars on the backend or import a CSV, then open it here.'}
		/>
	{:else}
		<div class="grid items-start gap-[30px] xl:grid-cols-[minmax(0,1fr)_26rem]">
			<div class="grid min-w-0 gap-[30px]">
				<Card.Root class="shadow-float">
					<Card.Content class="grid gap-4">
						<div class="flex flex-wrap items-center gap-x-4 gap-y-2 type-body-sm tabular-nums">
							<span class="font-medium">{bars.symbol}</span>
							{#if bars.timeframe}<Badge variant="secondary">{bars.timeframe}</Badge>{/if}
							{#if bars.origin === 'local'}<Badge variant="secondary">Imported</Badge>{/if}
							<span class="text-ink-muted">{bars.length.toLocaleString('en-US')} bars</span>
							<span class="text-ink-muted">
								{formatTime(bars.columns.time[0], intraday)} → {formatTime(
									bars.columns.time[bars.length - 1],
									intraday
								)} UTC
							</span>
							{#if bars.quality?.median_interval_seconds}
								<span class="text-ink-muted"
									>interval {formatDuration(bars.quality.median_interval_seconds)}</span
								>
							{/if}
							{#if bars.quality && bars.quality.gaps.length > 0}
								<span class="text-ink-muted"
									>{bars.quality.gaps.length} gap{bars.quality.gaps.length === 1 ? '' : 's'}</span
								>
							{/if}
							{#if bars.droppedRows > 0}
								<span class="text-ink-muted"
									>{formatValue(bars.droppedRows, 'int')} invalid rows dropped</span
								>
							{/if}
							{#if bars.duplicateRows > 0}
								<span class="text-ink-muted"
									>{formatValue(bars.duplicateRows, 'int')} duplicates collapsed</span
								>
							{/if}
							<div class="ml-auto flex items-center gap-2">
								<Switch
									id="volume"
									checked={explorer.showVolume}
									onCheckedChange={(v) => (explorer.showVolume = v)}
								/>
								<Label for="volume" class="type-caption">Volume</Label>
							</div>
						</div>
						<CandleChart
							columns={bars.columns}
							overlays={explorer.chart.overlays}
							panes={explorer.chart.panes}
							mask={explorer.eventMask}
							showVolume={explorer.showVolume}
							focus={explorer.focusRequest}
							{intraday}
							label="Price chart for {bars.symbol}"
						/>
					</Card.Content>
				</Card.Root>

				{#if explorer.study}
					<Card.Root>
						<Card.Content>
							<EventStudyPanel
								study={explorer.study}
								horizons={explorer.horizons}
								onhorizons={(h) => (explorer.horizons = h)}
								onsetOnly={explorer.onsetOnly}
								ononset={(v) => (explorer.onsetOnly = v)}
							/>
						</Card.Content>
					</Card.Root>

					<Card.Root>
						<Card.Header>
							<Card.Title class="type-body-sm">
								Matching bars
								<span class="font-normal text-ink-muted tabular-nums"
									>({explorer.matches.length.toLocaleString('en-US')}, newest first)</span
								>
							</Card.Title>
							<Card.Description>Select a row to centre the chart on that bar.</Card.Description>
						</Card.Header>
						<Card.Content>
							<MatchesTable
								columns={bars.columns}
								matches={explorer.matches}
								fields={matchFields}
								{intraday}
								onselect={(i) => explorer.focusBar(i)}
							/>
						</Card.Content>
					</Card.Root>
				{/if}
			</div>

			<aside class="grid gap-[30px] xl:sticky xl:top-[76px]">
				<Card.Root>
					<Card.Content><IndicatorPanel {explorer} /></Card.Content>
				</Card.Root>
				<Card.Root>
					<Card.Content>
						<FilterBuilder
							tree={explorer.filter}
							editor={explorer.filterEditor}
							{catalog}
							evaluation={explorer.evaluation}
							saved={explorerFilters}
							unit="bars"
						/>
					</Card.Content>
				</Card.Root>
			</aside>
		</div>
	{/if}
</div>
