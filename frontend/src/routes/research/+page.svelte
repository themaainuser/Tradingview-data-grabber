<script lang="ts">
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import FlaskConical from '@lucide/svelte/icons/flask-conical';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Card from '$lib/components/ui/card';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import FilterBuilder from '$lib/components/filters/FilterBuilder.svelte';
	import ColumnPicker from '$lib/components/research/ColumnPicker.svelte';
	import EquityCompare from '$lib/components/research/EquityCompare.svelte';
	import ResultDetail from '$lib/components/research/ResultDetail.svelte';
	import ResultsTable from '$lib/components/research/ResultsTable.svelte';
	import RunForm from '$lib/components/research/RunForm.svelte';
	import { createResearchCatalog } from '$lib/research/catalog';
	import { getApp } from '$lib/state/app.svelte';

	const { datasets, research, researchFilters } = getApp();

	const table = $derived(research.table);
	const catalog = $derived(table ? createResearchCatalog(table) : null);
	const active = $derived(research.report?.results.find((r) => r.id === research.activeId) ?? null);
</script>

<div class="grid gap-[30px]">
	<header class="grid gap-2">
		<h1 class="type-display-md">Research</h1>
		<p class="max-w-xl type-body text-pretty text-ink-muted">
			Run the backend's strategy grid over your captures, then screen results with the same compound
			filters.
		</p>
	</header>

	<div class="grid items-start gap-[30px] lg:grid-cols-[20rem_minmax(0,1fr)]">
		<Card.Root class="lg:sticky lg:top-[76px]">
			<Card.Content><RunForm {research} {datasets} /></Card.Content>
		</Card.Root>

		<div class="grid min-w-0 gap-[30px]">
			{#if research.status === 'error' && research.error}
				<ErrorPanel
					error={research.error}
					title="Research run failed"
					onretry={() => research.run()}
				/>
			{/if}

			{#if research.status === 'loading' && !table}
				<div class="grid gap-3" aria-busy="true" aria-label="Running research">
					<Skeleton class="h-6 w-1/3" />
					<Skeleton class="h-72 w-full" />
				</div>
			{:else if !table || !catalog || !research.report}
				{#if research.status !== 'error'}
					<EmptyState
						tone="magenta"
						icon={FlaskConical}
						title="No research run yet"
						description="Choose one or more datasets, set the cost and annualisation, then run. Results appear here once the backend returns them."
					/>
				{/if}
			{:else}
				{@const report = research.report}
				<Card.Root>
					<Card.Content class="grid gap-4">
						<div
							class="flex flex-wrap items-center gap-x-4 gap-y-1 type-caption text-ink-muted tabular-nums"
							aria-busy={research.status === 'loading'}
						>
							<span>{report.assets.length} dataset{report.assets.length === 1 ? '' : 's'}</span>
							<span>{report.results.length.toLocaleString('en-US')} strategies</span>
							<span>{report.metadata.fee_bps_per_position_change} bps per position change</span>
							<span>{report.metadata.periods_per_year.toLocaleString('en-US')} periods / year</span>
							{#if research.status === 'loading'}<span class="text-ink">Refreshing…</span>{/if}
						</div>
						<FilterBuilder
							tree={research.filter}
							editor={research.filterEditor}
							{catalog}
							evaluation={research.evaluation}
							saved={researchFilters}
							unit="strategies"
						/>
					</Card.Content>
				</Card.Root>

				<Card.Root>
					<Card.Header class="flex-row items-center">
						<Card.Title class="type-body-sm">
							Results <span class="font-normal text-ink-muted tabular-nums"
								>({research.order.length.toLocaleString('en-US')})</span
							>
						</Card.Title>
						<div class="ml-auto">
							<ColumnPicker
								columns={table.columns}
								visible={research.visibleColumns}
								ontoggle={(k) => research.toggleColumn(k)}
							/>
						</div>
					</Card.Header>
					<Card.Content class="grid gap-3">
						<ResultsTable {research} {table} />
						<p class="type-caption text-pretty text-ink-muted">
							Sorting or filtering many permutations creates selection bias: prefer forward-fold
							consistency over any single best number.
						</p>
					</Card.Content>
				</Card.Root>

				<Card.Root>
					<Card.Header><Card.Title class="type-body-sm">Equity curves</Card.Title></Card.Header>
					<Card.Content><EquityCompare {table} ids={research.compareIds} /></Card.Content>
				</Card.Root>

				{#if active}
					<Card.Root>
						<Card.Content
							><ResultDetail
								result={active}
								onclose={() => (research.activeId = null)}
							/></Card.Content
						>
					</Card.Root>
				{/if}

				{#if report.model_notes.length > 0}
					<Card.Root>
						<Card.Header>
							<Card.Title class="type-body-sm">Model notes</Card.Title>
							<Card.Description
								>Output from an external language model; it does not affect the ranking.</Card.Description
							>
						</Card.Header>
						<Card.Content class="grid gap-3">
							{#each report.model_notes as note (note.model)}
								<div class="rounded-lg bg-canvas p-[15px]">
									<p class="type-caption font-medium">
										{note.model} <span class="text-ink-muted">({note.status})</span>
									</p>
									<p class="mt-1 type-body-sm whitespace-pre-wrap">{note.text}</p>
								</div>
							{/each}
						</Card.Content>
					</Card.Root>
				{/if}

				<!-- faq-row: canvas ground, hairline-soft divider, 24px padding -->
				<Collapsible.Root class="group/faq border-t border-hairline-soft">
					<Collapsible.Trigger
						class="flex w-full items-center justify-between gap-[15px] rounded-md py-5 text-left type-body text-ink"
					>
						Method and disclosures
						<ChevronDown
							class="size-4 text-ink-muted transition-transform duration-150 ease-out group-data-[state=open]/faq:rotate-180"
							aria-hidden="true"
						/>
					</Collapsible.Trigger>
					<Collapsible.Content class="grid gap-3 pb-5 type-body text-ink-muted">
						<p class="text-pretty">{report.metadata.forward_validation}</p>
						<ul class="list-disc pl-5">
							{#each report.disclosures as text (text)}<li class="text-pretty">{text}</li>{/each}
						</ul>
					</Collapsible.Content>
				</Collapsible.Root>
			{/if}
		</div>
	</div>
</div>
