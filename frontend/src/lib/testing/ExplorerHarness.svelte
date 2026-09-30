<script lang="ts">
	import CandleChart from '$lib/components/app/CandleChart.svelte';
	import FilterBuilder from '$lib/components/filters/FilterBuilder.svelte';
	import IndicatorPanel from '$lib/components/explorer/IndicatorPanel.svelte';
	import EventStudyPanel from '$lib/components/explorer/EventStudyPanel.svelte';
	import MatchesTable from '$lib/components/explorer/MatchesTable.svelte';
	import { createExplorerCatalog } from '$lib/explorer/catalog';
	import { fieldLabel } from '$lib/explorer/fields';
	import type { ExplorerStore } from '$lib/state/explorer.svelte';
	import type { SavedFilters } from '$lib/state/saved-filters.svelte';

	// Test-only composition of the explorer building blocks (the route itself needs SvelteKit's
	// router state, which is not available in a component test).
	let { explorer, saved }: { explorer: ExplorerStore; saved: SavedFilters } = $props();
	const catalog = createExplorerCatalog();
	const bars = $derived(explorer.bars!);
	const fields = $derived(
		explorer.referencedFields.flatMap((key) => {
			const values = explorer.source?.numeric(key);
			return values ? [{ key, label: fieldLabel(key), values }] : [];
		})
	);
</script>

<CandleChart
	columns={bars.columns}
	overlays={explorer.chart.overlays}
	panes={explorer.chart.panes}
	mask={explorer.eventMask}
	showVolume={explorer.showVolume}
	label="Test chart"
/>
<IndicatorPanel {explorer} />
<FilterBuilder
	tree={explorer.filter}
	editor={explorer.filterEditor}
	{catalog}
	evaluation={explorer.evaluation}
	{saved}
	unit="bars"
/>
{#if explorer.study}
	<EventStudyPanel
		study={explorer.study}
		horizons={explorer.horizons}
		onhorizons={(h) => (explorer.horizons = h)}
		onsetOnly={explorer.onsetOnly}
		ononset={(v) => (explorer.onsetOnly = v)}
	/>
	<MatchesTable
		columns={bars.columns}
		matches={explorer.matches}
		{fields}
		intraday
		onselect={(i) => explorer.focusBar(i)}
	/>
{/if}
