<script lang="ts">
	import ShieldCheck from '@lucide/svelte/icons/shield-check';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import type { VerdictStore } from '$lib/state/verdict.svelte';
	import { count } from '$lib/verdict/present';

	interface Props {
		store: VerdictStore;
	}

	let { store }: Props = $props();

	const ledger = $derived(store.state?.ledger ?? null);
	let open = $state(false);

	// The entry list is fetched when first opened, and again after anything changed the ledger.
	$effect(() => {
		if (open && store.ledgerStatus === 'idle') store.loadLedger();
	});
</script>

{#if ledger}
	<section
		class="grid grid-cols-[minmax(0,1fr)] gap-[15px]"
		aria-labelledby="ledger-title"
		data-testid="ledger-section"
	>
		<h2 id="ledger-title" class="type-headline">Trial ledger</h2>
		<div class="grid grid-cols-[minmax(0,1fr)] gap-4 rounded-xl bg-surface-1 p-5">
			<dl class="grid grid-cols-2 gap-x-5 gap-y-3 tabular-nums sm:grid-cols-4">
				<div>
					<dt class="type-caption text-ink-muted">Rules tried on this dataset (N)</dt>
					<dd class="type-display-md" data-testid="ledger-n">{count(ledger.trials_dataset)}</dd>
				</div>
				<div>
					<dt class="type-caption text-ink-muted">Runs on this dataset</dt>
					<dd class="type-display-md">{count(ledger.runs_dataset)}</dd>
				</div>
				<div>
					<dt class="type-caption text-ink-muted">Rules tried, all datasets</dt>
					<dd class="type-display-md">{count(ledger.trials_total)}</dd>
				</div>
				<div>
					<dt class="type-caption text-ink-muted">Ledger chain</dt>
					<dd class="flex items-center gap-2 type-body-sm" data-testid="ledger-chain">
						{#if ledger.intact}
							<ShieldCheck class="size-4 text-success-ink" aria-hidden="true" /> Intact
						{:else}
							<TriangleAlert class="size-4 text-coral-ink" aria-hidden="true" /> Broken
						{/if}
					</dd>
				</div>
			</dl>
			<p class="max-w-[72ch] type-caption text-pretty text-ink-muted">
				N counts every distinct rule ever run on this dataset, including failed runs. It comes from
				the ledger, not from this page, and cannot be edited here. Re-running with different costs
				adds a run but never changes N. The ledger is append-only and hash-chained, so editing it by
				hand is detectable; it is tamper-evident, not tamper-proof.
			</p>
			{#if !ledger.intact}
				<p class="type-body-sm text-pretty text-coral-ink" role="alert" data-testid="ledger-broken">
					The ledger&rsquo;s hash chain does not verify, so N can no longer be trusted. Running,
					freezing and reading the holdout are disabled until the file is restored.
				</p>
			{/if}

			<Collapsible.Root bind:open>
				<Collapsible.Trigger
					class="group/ledger flex items-center gap-2 rounded-md type-body-sm text-ink-muted hover:text-ink"
				>
					Show ledger entries
					<ChevronDown
						class="size-4 transition-transform duration-150 ease-out group-data-[state=open]/ledger:rotate-180"
						aria-hidden="true"
					/>
				</Collapsible.Trigger>
				<Collapsible.Content>
					<div class="mt-3" aria-live="polite">
						{#if store.ledgerStatus === 'loading'}
							<p class="type-caption text-ink-muted">Loading the ledger&hellip;</p>
						{:else if store.ledgerError}
							<p class="type-caption text-coral-ink" role="alert">{store.ledgerError.message}</p>
						{:else if store.ledger}
							<ol class="grid gap-1.5" data-testid="ledger-entries">
								{#each store.ledger.entries as entry (entry.seq)}
									<li
										class="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 rounded-lg bg-canvas px-3 py-2 tabular-nums"
									>
										<span class="type-caption text-ink-muted">#{entry.seq}</span>
										<span class="min-w-0">
											<span class="type-body-sm text-pretty">{entry.summary}</span>
											<span class="block type-micro break-all text-ink-muted"
												>{entry.at} &middot;
												<span class="font-mono">{entry.hash.slice(0, 12)}</span></span
											>
										</span>
									</li>
								{/each}
							</ol>
							{#if store.ledger.total_entries > store.ledger.entries.length}
								<p class="mt-2 type-caption text-ink-muted">
									Showing the latest {count(store.ledger.entries.length)} of {count(
										store.ledger.total_entries
									)}
									entries.
								</p>
							{/if}
						{/if}
					</div>
				</Collapsible.Content>
			</Collapsible.Root>
		</div>
	</section>
{/if}
