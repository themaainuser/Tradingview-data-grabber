<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import ArrowUpDown from '@lucide/svelte/icons/arrow-up-down';
	import Download from '@lucide/svelte/icons/download';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { TableView } from '$lib/api/providers';
	import { filterRows, formatCell, sortRows, toCsv } from '$lib/providers/format';
	import ExternalLink from '../ExternalLink.svelte';

	let { view }: { view: TableView } = $props();

	const PAGE = 25;
	let text = $state('');
	let sort = $state<{ column: number; descending: boolean } | null>(null);
	let page = $state(0);

	const matching = $derived(filterRows(view.rows, text));
	const ordered = $derived(sort ? sortRows(matching, sort.column, sort.descending) : matching);
	const pages = $derived(Math.max(1, Math.ceil(ordered.length / PAGE)));
	const current = $derived(Math.min(page, pages - 1));
	const shown = $derived(ordered.slice(current * PAGE, current * PAGE + PAGE));

	function sortBy(column: number) {
		page = 0;
		if (sort?.column !== column) sort = { column, descending: false };
		else if (!sort.descending) sort = { column, descending: true };
		else sort = null;
	}

	const ariaSort = (column: number) =>
		sort?.column === column ? (sort.descending ? 'descending' : 'ascending') : 'none';

	function download() {
		const blob = new Blob([toCsv(view.columns, ordered)], { type: 'text/csv;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = `${view.id}.csv`;
		link.click();
		URL.revokeObjectURL(url);
	}

	const first = $derived(ordered.length === 0 ? 0 : current * PAGE + 1);
	const last = $derived(Math.min(ordered.length, current * PAGE + PAGE));
</script>

<SectionCard id="view-{view.id}" title={view.title} description={view.subtitle ?? undefined}>
	{#snippet actions()}
		{#if view.rows.length > PAGE}
			<Input
				type="search"
				placeholder="Filter rows"
				aria-label="Filter rows of {view.title}"
				class="w-44"
				bind:value={text}
				oninput={() => (page = 0)}
			/>
		{/if}
		<Button variant="translucent" size="sm" onclick={download}>
			<Download aria-hidden="true" /> CSV
		</Button>
	{/snippet}

	<!-- A scrollable region must be reachable by keyboard so wide tables can be scrolled without a mouse. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="max-w-full overflow-x-auto rounded-lg"
		role="region"
		aria-label="{view.title} table"
		tabindex="0"
	>
		<table class="w-full border-collapse type-body-sm">
			<thead>
				<tr class="border-b border-hairline text-left">
					{#each view.columns as column, c (column.key)}
						{@const numeric = column.type === 'number' || column.type === 'percent'}
						<th
							scope="col"
							aria-sort={ariaSort(c)}
							class="p-0 font-medium whitespace-nowrap text-ink-muted {numeric ? 'text-right' : ''}"
						>
							<button
								type="button"
								onclick={() => sortBy(c)}
								class="inline-flex w-full items-center gap-1 px-3 py-2 hover:text-ink pointer-coarse:min-h-11 {numeric
									? 'justify-end'
									: ''}"
							>
								{column.label}
								{#if sort?.column === c}
									{#if sort.descending}<ArrowDown class="size-3.5" aria-hidden="true" />
									{:else}<ArrowUp class="size-3.5" aria-hidden="true" />{/if}
								{:else}
									<ArrowUpDown class="size-3.5 opacity-40" aria-hidden="true" />
								{/if}
							</button>
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each shown as row, r (current * PAGE + r)}
					<tr class="border-b border-hairline-soft last:border-0">
						{#each row as cell, c (view.columns[c].key)}
							{@const type = view.columns[c].type}
							<td
								class="px-3 py-2 align-top {type === 'number' || type === 'percent'
									? 'text-right tabular-nums'
									: type === 'date' || type === 'datetime'
										? 'whitespace-nowrap tabular-nums'
										: 'max-w-[44ch]'}"
							>
								{#if type === 'url' && typeof cell === 'string'}
									<ExternalLink href={cell}>{cell}</ExternalLink>
								{:else}
									{formatCell(cell, type)}
								{/if}
							</td>
						{/each}
					</tr>
				{:else}
					<tr>
						<td colspan={view.columns.length} class="px-3 py-6 text-center text-ink-muted">
							No rows match "{text}".
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<div class="flex flex-wrap items-center justify-between gap-3 type-caption text-ink-muted">
		<span data-testid="row-range" aria-live="polite">
			Rows {first.toLocaleString('en-US')}&ndash;{last.toLocaleString('en-US')} of {ordered.length.toLocaleString(
				'en-US'
			)}{ordered.length !== view.total_rows
				? ` (filtered from ${view.total_rows.toLocaleString('en-US')})`
				: ''}
		</span>
		{#if pages > 1}
			<div class="flex items-center gap-2">
				<Button
					variant="translucent"
					size="xs"
					disabled={current === 0}
					onclick={() => (page = current - 1)}>Previous</Button
				>
				<span class="tabular-nums">Page {current + 1} of {pages}</span>
				<Button
					variant="translucent"
					size="xs"
					disabled={current >= pages - 1}
					onclick={() => (page = current + 1)}>Next</Button
				>
			</div>
		{/if}
	</div>
	{#if view.truncated}
		<p class="type-caption text-ink-muted" data-testid="table-truncated">
			The provider returned {view.total_rows.toLocaleString('en-US')} rows; the first {view.rows.length.toLocaleString(
				'en-US'
			)} are included.
		</p>
	{/if}
</SectionCard>
