<script lang="ts">
	import VirtualList from '$lib/components/app/VirtualList.svelte';

	let {
		count,
		itemHeight = 30,
		height = 300
	}: { count: number; itemHeight?: number; height?: number } = $props();
</script>

<div style:height="{height}px">
	<VirtualList {count} {itemHeight} label="Test rows" class="h-full">
		{#snippet header()}<div>Header</div>{/snippet}
		{#snippet row(index)}<div data-testid="virtual-row">Row {index}</div>{/snippet}
		{#snippet empty()}<p>Nothing here</p>{/snippet}
	</VirtualList>
</div>
