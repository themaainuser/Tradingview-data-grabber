<script lang="ts">
	import type { ProviderView } from '$lib/api/providers';
	import BarsPanel from './BarsPanel.svelte';
	import FactsPanel from './FactsPanel.svelte';
	import FeedPanel from './FeedPanel.svelte';
	import HeatmapPanel from './HeatmapPanel.svelte';
	import SeriesPanel from './SeriesPanel.svelte';
	import TablePanel from './TablePanel.svelte';
	import TextPanel from './TextPanel.svelte';

	let { view }: { view: ProviderView } = $props();
</script>

{#if view.kind === 'series'}
	<SeriesPanel {view} />
{:else if view.kind === 'table'}
	<TablePanel {view} />
{:else if view.kind === 'facts'}
	<FactsPanel {view} />
{:else if view.kind === 'bars'}
	<BarsPanel {view} />
{:else if view.kind === 'feed'}
	<FeedPanel {view} />
{:else if view.kind === 'heatmap'}
	<HeatmapPanel {view} />
{:else if view.kind === 'text'}
	<TextPanel {view} />
{/if}
