<script lang="ts">
	import VirtualList from '$lib/components/app/VirtualList.svelte';
	import { formatTime } from '$lib/charts/scale';
	import { formatValue } from '$lib/format';
	import type { OhlcvColumns } from '$lib/indicators/types';

	interface FieldColumn {
		key: string;
		label: string;
		values: Float64Array;
	}

	interface Props {
		columns: OhlcvColumns;
		/** Matching bar indexes, oldest first. */
		matches: Uint32Array;
		/** Extra columns for fields used by the filter. */
		fields: readonly FieldColumn[];
		intraday: boolean;
		onselect: (barIndex: number) => void;
	}

	let { columns, matches, fields, intraday, onselect }: Props = $props();

	// Newest match first: the freshest signals matter most.
	const barAt = (row: number) => matches[matches.length - 1 - row];
	const template = $derived(`10rem repeat(${3 + fields.length}, minmax(6.5rem, 1fr))`);
	const minWidth = $derived(160 + (3 + fields.length) * 104);
</script>

<VirtualList
	count={matches.length}
	itemHeight={30}
	label="Bars matching the filter"
	{minWidth}
	class="max-h-96 rounded-lg bg-canvas"
	key={(row) => barAt(row)}
>
	{#snippet header()}
		<div
			class="grid gap-2 px-3 py-2 type-caption font-medium text-ink-muted"
			style:grid-template-columns={template}
		>
			<span role="columnheader">Time (UTC)</span>
			<span role="columnheader" class="text-right">Close</span>
			<span role="columnheader" class="text-right">Volume</span>
			<span role="columnheader" class="text-right">Bar change</span>
			{#each fields as field (field.key)}
				<span role="columnheader" class="truncate text-right" title={field.label}
					>{field.label}</span
				>
			{/each}
		</div>
	{/snippet}
	{#snippet row(index)}
		{@const bar = barAt(index)}
		{@const change = (columns.close[bar] / columns.open[bar] - 1) * 100}
		<button
			type="button"
			class="grid h-full w-full cursor-pointer items-center gap-2 px-3 text-left type-body-sm tabular-nums transition-colors duration-100 ease-out outline-none hover:bg-surface-2 focus-visible:bg-surface-2"
			style:grid-template-columns={template}
			onclick={() => onselect(bar)}
			aria-label="Centre chart on {formatTime(columns.time[bar], intraday)}"
		>
			<span>{formatTime(columns.time[bar], intraday)}</span>
			<span class="text-right">{formatValue(columns.close[bar], 'price')}</span>
			<span class="text-right">{formatValue(columns.volume[bar], 'compact')}</span>
			<span class="text-right {change >= 0 ? 'text-positive' : 'text-negative'}"
				>{formatValue(change, 'pct')}</span
			>
			{#each fields as field (field.key)}
				<span class="text-right">{formatValue(field.values[bar], 'number')}</span>
			{/each}
		</button>
	{/snippet}
	{#snippet empty()}
		<p class="px-3 py-8 text-center type-body text-ink-muted">No bars match the current filter.</p>
	{/snippet}
</VirtualList>
