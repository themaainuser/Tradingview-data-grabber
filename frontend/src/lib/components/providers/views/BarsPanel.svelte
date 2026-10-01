<script lang="ts">
	import BarChart from '$lib/components/charts/BarChart.svelte';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { BarsView } from '$lib/api/providers';
	import { formatFact } from '$lib/providers/format';

	let { view }: { view: BarsView } = $props();

	const format = (v: number) => formatFact({ value: v, format: view.format });
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	<BarChart
		labels={view.labels}
		values={view.values}
		colorBy={view.sign_colors ? 'sign' : 'solid'}
		{format}
		label="{view.title}: {view.value_label} by {view.labels.length} categories"
	/>
</SectionCard>
