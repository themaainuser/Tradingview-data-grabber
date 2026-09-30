<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Scale from '@lucide/svelte/icons/scale';
	import * as Card from '$lib/components/ui/card';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import * as Select from '$lib/components/ui/select';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import HoldoutPanel from '$lib/components/verdict/HoldoutPanel.svelte';
	import IntegrityPanel from '$lib/components/verdict/IntegrityPanel.svelte';
	import LedgerPanel from '$lib/components/verdict/LedgerPanel.svelte';
	import RulesTable from '$lib/components/verdict/RulesTable.svelte';
	import RunPanel from '$lib/components/verdict/RunPanel.svelte';
	import StatisticsPanel from '$lib/components/verdict/StatisticsPanel.svelte';
	import VerdictBanner from '$lib/components/verdict/VerdictBanner.svelte';
	import { getApp } from '$lib/state/app.svelte';

	const { datasets, verdict } = getApp();

	const requested = $derived(page.params.dataset ?? null);

	// URL -> store: a link, reload or shared URL opens that dataset's ledger and latest verdict.
	$effect(() => {
		const id = requested;
		if (!id) return;
		untrack(() => {
			if (verdict.datasetId !== id || verdict.status === 'idle') verdict.open(id);
		});
	});

	function choose(id: string) {
		goto(resolve('/verdict/[[dataset]]', { dataset: id }), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	const report = $derived(verdict.report);
	const selected = $derived(datasets.usable.find((d) => d.id === requested));
	const selectedLabel = $derived(
		selected
			? `${selected.symbol}${selected.timeframe ? ` \u00b7 ${selected.timeframe}` : ''}`
			: 'Choose a dataset'
	);
	let about = $state(false);
</script>

<svelte:head>
	<title>Verdict · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-[60px]">
	<header class="grid max-w-[860px] gap-5">
		<p class="type-caption text-ink-muted">Honest verdict engine</p>
		<h1 class="type-display-lg">Verdict</h1>
		<p class="max-w-[60ch] type-body-lg text-ink-muted">
			Says what a dataset can and cannot support before anything is ranked. Every rule tried is
			counted, the most recent bars stay sealed until the end, costs are charged on both sides of
			every trade, and a rule that barely trades gets no Sharpe at all.
		</p>
		<div class="grid gap-3">
			<Select.Root
				type="single"
				value={requested ?? ''}
				onValueChange={choose}
				disabled={datasets.usable.length === 0}
			>
				<Select.Trigger class="w-72" aria-label="Dataset">{selectedLabel}</Select.Trigger>
				<Select.Content>
					{#each datasets.usable as d (d.id)}
						<Select.Item value={d.id} label={d.symbol}>
							{d.symbol}{d.timeframe ? ` \u00b7 ${d.timeframe}` : ''}
							<span class="ml-auto type-caption text-ink-muted tabular-nums"
								>{d.rows.toLocaleString('en-US')}</span
							>
						</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>

			<Collapsible.Root bind:open={about}>
				<Collapsible.Trigger
					class="group/about flex items-center gap-2 rounded-md type-body-sm text-ink-muted hover:text-ink"
				>
					How to read this page
					<ChevronDown
						class="size-4 transition-transform duration-150 ease-out group-data-[state=open]/about:rotate-180"
						aria-hidden="true"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content>
					<ol
						class="mt-3 grid max-w-[68ch] list-decimal gap-2 pl-5 type-body-sm text-pretty text-ink-muted"
					>
						<li>
							The first run seals the most recent bars. Nothing on this page, and no research query,
							ever sees them.
						</li>
						<li>
							Each rule is simulated with signals on a bar&rsquo;s close and fills at the next open,
							with fee, spread and slippage on both sides.
						</li>
						<li>
							A rule needs a minimum number of trades before it gets any statistic. Below that it is
							listed as not tested.
						</li>
						<li>
							Rules that qualify are tested for luck with a block bootstrap, deflated for how many
							rules were tried, and re-run at 1.5&times; and 2&times; costs.
						</li>
						<li>
							The verdict is one of three labels. Only a candidate can unlock a single look at the
							sealed holdout, which at this length is a sanity check, not proof.
						</li>
					</ol>
				</Collapsible.Content>
			</Collapsible.Root>
		</div>
	</header>

	{#if datasets.status === 'ready' && datasets.usable.length === 0}
		<EmptyState
			tone="violet"
			icon={Scale}
			title="No backend datasets to assess"
			description="The verdict is computed and recorded by the backend, so it needs captures there; files imported in the browser are not available. Capture bars, then press Refresh on the Datasets page."
		/>
	{:else if !requested}
		<EmptyState
			icon={Scale}
			title="Choose a dataset"
			description="Pick a capture above to see its trial ledger, seal its holdout and run the verdict."
		/>
	{:else if verdict.status === 'error' && verdict.error && !verdict.state}
		<ErrorPanel
			error={verdict.error}
			title="Could not load the verdict"
			onretry={() => verdict.reload()}
		/>
	{:else if !verdict.state}
		<div class="grid gap-[30px]" aria-busy="true" aria-label="Loading the verdict">
			<Skeleton class="h-64 w-full" />
			<Skeleton class="h-72 w-full" />
		</div>
	{:else}
		<div
			class="grid grid-cols-[minmax(0,1fr)] items-start gap-[30px] lg:grid-cols-[22rem_minmax(0,1fr)]"
		>
			<!-- Not sticky: the form is taller than a short viewport, and a sticky card that tall hides its own Run button. -->
			<Card.Root>
				<Card.Content><RunPanel store={verdict} /></Card.Content>
			</Card.Root>

			<div class="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-[30px]">
				{#if verdict.status === 'error' && verdict.error}
					<ErrorPanel
						error={verdict.error}
						title="Could not refresh"
						onretry={() => verdict.reload()}
					/>
				{/if}

				{#if report}
					<VerdictBanner {report} />
					<RulesTable rules={report.rules} minTrades={report.settings.min_trades} />
					<StatisticsPanel {report} />
				{:else}
					<div
						class="grid gap-3 rounded-xl bg-surface-1 p-[30px]"
						data-testid="no-verdict"
						aria-live="polite"
					>
						<h2 class="type-headline">No verdict yet</h2>
						<p class="max-w-[62ch] type-body text-pretty text-ink-muted">
							{verdict.runStatus === 'loading'
								? 'Running the verdict. This simulates every rule at three cost levels and can take a few seconds.'
								: 'Nothing has been run on this dataset. Choose the settings and press the button to seal the holdout and run the verdict. Nothing here is estimated in advance.'}
						</p>
					</div>
				{/if}

				<HoldoutPanel store={verdict} />
				<LedgerPanel store={verdict} />
				{#if report}
					<IntegrityPanel {report} />
					{#if report.notes.length}
						<ul
							class="grid max-w-[76ch] list-disc gap-1.5 pl-5 type-caption text-pretty text-ink-muted"
						>
							{#each report.notes as note (note)}
								<li>{note}</li>
							{/each}
						</ul>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>
