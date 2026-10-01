<script lang="ts">
	import Heatmap from '$lib/components/charts/Heatmap.svelte';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { HeatmapView } from '$lib/api/providers';

	let { view }: { view: HeatmapView } = $props();

	const format = (v: number) => (Math.abs(v) >= 1000 ? v.toExponential(2) : v.toFixed(2));
	const legend = $derived(
		view.domain
			? { low: format(view.domain[0]), high: format(view.domain[1]) }
			: { low: 'Lower', high: 'Higher' }
	);
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	<Heatmap
		rows={view.rows}
		cols={view.cols}
		values={view.values}
		scale={view.scale}
		domain={view.domain ?? undefined}
		{format}
		showValues
		square
		{legend}
		label="{view.title} matrix of {view.rows.length} by {view.cols.length}"
	/>
</SectionCard>
