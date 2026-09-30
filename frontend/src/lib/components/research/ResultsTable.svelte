<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import VirtualList from '$lib/components/app/VirtualList.svelte';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { formatValue } from '$lib/format';
	import type { ResearchColumn, ResearchTable } from '$lib/research/columns';
	import type { ResearchStore } from '$lib/state/research.svelte';

	interface Props {
		research: ResearchStore;
		table: ResearchTable;
	}

	let { research, table }: Props = $props();

	const columns = $derived(
		research.visibleColumns
			.map((key) => table.column(key))
			.filter((c): c is ResearchColumn => c !== undefined)
	);
	const template = $derived(
		`2rem ${columns.map((c) => (c.kind === 'text' ? 'minmax(11rem, 1.5fr)' : 'minmax(7.5rem, 1fr)')).join(' ')}`
	);
	const minWidth = $derived(
		32 + columns.reduce((sum, c) => sum + (c.kind === 'text' ? 176 : 120), 0)
	);

	const GROUP_SHORT: Record<string, string> = {
		'Full sample': 'Full',
		'In-sample': 'In',
		Forward: 'Fwd',
		'Forward folds': 'Folds',
		'Versus buy-and-hold': 'vs B&H'
	};

	function tone(column: ResearchColumn, value: number): string {
		if (column.higherIsBetter !== true || !Number.isFinite(value)) return '';
		return value > 0 ? 'text-positive' : value < 0 ? 'text-negative' : '';
	}

	const rowId = (row: number) => table.rows[research.order[row]].id;
</script>

<VirtualList
	count={research.order.length}
	itemHeight={34}
	label="Strategy results"
	{minWidth}
	class="max-h-[32rem] rounded-lg bg-canvas"
	key={rowId}
>
	{#snippet header()}
		<div
			class="grid items-center gap-2 px-3 py-1.5 type-caption"
			style:grid-template-columns={template}
		>
			<span role="columnheader" aria-label="Compare"></span>
			{#each columns as column (column.key)}
				<span
					role="columnheader"
					aria-sort={research.sortKey === column.key
						? research.sortDir === 'asc'
							? 'ascending'
							: 'descending'
						: 'none'}
					class={column.kind === 'text' ? '' : 'text-right'}
				>
					<button
						type="button"
						class="inline-flex max-w-full items-center gap-1 rounded-sm font-medium text-ink-muted transition-colors duration-100 ease-out outline-none hover:text-ink"
						title="{column.group}: {column.description}"
						onclick={() => research.setSort(column.key)}
					>
						<span class="truncate">
							{#if GROUP_SHORT[column.group]}<span class="font-normal"
									>{GROUP_SHORT[column.group]} ·</span
								>{/if}
							{column.label}
						</span>
						{#if research.sortKey === column.key}
							{#if research.sortDir === 'asc'}<ArrowUp
									class="size-3 shrink-0"
									aria-hidden="true"
								/>{:else}<ArrowDown class="size-3 shrink-0" aria-hidden="true" />{/if}
						{/if}
					</button>
				</span>
			{/each}
		</div>
	{/snippet}
	{#snippet row(index)}
		{@const source = research.order[index]}
		{@const id = table.rows[source].id}
		<div
			class="grid h-full items-center gap-2 px-3 type-body-sm tabular-nums transition-colors duration-100 ease-out hover:bg-surface-2 {research.activeId ===
			id
				? 'bg-muted'
				: ''}"
			style:grid-template-columns={template}
			role="presentation"
		>
			<span role="cell">
				<Checkbox
					checked={research.compareIds.includes(id)}
					onCheckedChange={() => research.toggleCompare(id)}
					aria-label="Compare {table.rows[source].name} on {table.rows[source].symbol}"
				/>
			</span>
			{#each columns as column (column.key)}
				{@const value = table.cell(source, column.key)}
				{#if column.kind === 'text'}
					<span role="cell" class="min-w-0">
						<button
							type="button"
							class="block max-w-full truncate rounded-sm text-left outline-none {column.key ===
							'name'
								? 'hover:underline'
								: ''}"
							onclick={() => research.open(id)}
						>
							{value}
						</button>
					</span>
				{:else}
					<span role="cell" class="text-right {tone(column, value as number)}"
						>{formatValue(value as number, column.format)}</span
					>
				{/if}
			{/each}
		</div>
	{/snippet}
	{#snippet empty()}
		<p class="px-3 py-10 text-center type-body text-ink-muted">
			No strategies match the current filter.
		</p>
	{/snippet}
</VirtualList>
