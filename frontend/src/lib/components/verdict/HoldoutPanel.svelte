<script lang="ts">
	import Lock from '@lucide/svelte/icons/lock';
	import Snowflake from '@lucide/svelte/icons/snowflake';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Label } from '$lib/components/ui/label';
	import type { VerdictStore } from '$lib/state/verdict.svelte';
	import { MAX_FINALISTS } from '$lib/state/verdict.svelte';
	import { count, pctOf, utc } from '$lib/verdict/present';
	import WindowTable from './WindowTable.svelte';

	interface Props {
		store: VerdictStore;
	}

	let { store }: Props = $props();

	const vs = $derived(store.state);
	const holdout = $derived(vs?.holdout ?? null);
	const report = $derived(store.report);
	const freeze = $derived(vs?.freeze ?? null);
	const result = $derived(vs?.holdout_read ?? null);
	const isCandidate = $derived(report?.verdict.label === 'CANDIDATE');

	// An explicit acknowledgement is required before the one-way read; it resets with the dataset.
	let understood = $state(false);
	$effect(() => {
		void store.datasetId;
		understood = false;
	});
</script>

{#if holdout}
	<section
		class="grid grid-cols-[minmax(0,1fr)] gap-[15px]"
		aria-labelledby="holdout-title"
		data-testid="holdout-section"
	>
		<div class="grid gap-1">
			<h2 id="holdout-title" class="type-headline">Sealed holdout</h2>
			<p class="max-w-[72ch] type-caption text-pretty text-ink-muted tabular-nums">
				The most recent {pctOf(holdout.fraction)} of the bars ({count(holdout.bars)} bars, {utc(
					holdout.start,
					false
				)} to {utc(holdout.end, false)}) was set aside before any analysis and excluded from every
				research query. It can be read once.
			</p>
		</div>

		<div class="grid grid-cols-[minmax(0,1fr)] gap-4 rounded-xl bg-surface-1 p-5">
			<p class="flex items-center gap-2 type-body-sm" data-testid="holdout-status">
				<Lock class="size-4 shrink-0" aria-hidden="true" />
				{#if holdout.status === 'read'}
					Read on {holdout.read_at ? utc(holdout.read_at) : 'an earlier date'}. It cannot be read
					again.
				{:else}
					Unread and sealed.
				{/if}
			</p>

			{#if store.freezeError || store.readError}
				<p class="type-body-sm text-pretty text-coral-ink" role="alert" data-testid="read-error">
					{store.readError?.message ?? store.freezeError?.message}
				</p>
			{/if}

			{#if result}
				<div class="grid grid-cols-[minmax(0,1fr)] gap-3" data-testid="holdout-result">
					<p class="max-w-[72ch] type-body-sm text-pretty" data-testid="holdout-caveat">
						{result.caveat}
					</p>
					<WindowTable rules={result.rules} label="Holdout result for the frozen rules" />
					<p class="type-caption text-ink-muted tabular-nums">
						{count(result.bars)} bars, {utc(result.start, false)} to {utc(result.end, false)}.
					</p>
				</div>
			{:else if !report}
				<p class="type-body-sm text-pretty text-ink-muted" data-testid="holdout-locked">
					Locked. Run a verdict first: the holdout can only be read for a candidate.
				</p>
			{:else if !isCandidate && !freeze}
				<p class="type-body-sm text-pretty text-ink-muted" data-testid="holdout-locked">
					Locked. {report.verdict.label === 'INSUFFICIENT_DATA'
						? 'No rule qualified, so there is nothing to test on the holdout.'
						: 'No rule passed every check, so there is nothing to test on the holdout.'}
					It stays sealed until a run produces a candidate.
				</p>
			{:else if !freeze}
				<fieldset class="grid gap-3" data-testid="finalists">
					<legend class="mb-1 type-body-sm">
						Choose up to {MAX_FINALISTS} finalists to freeze
					</legend>
					<ul class="grid gap-2">
						{#each store.candidates as candidate (candidate.id)}
							<li class="flex items-center gap-2.5">
								<Checkbox
									id="finalist-{candidate.id}"
									checked={store.selectedRuleIds.includes(candidate.id)}
									disabled={!store.selectedRuleIds.includes(candidate.id) &&
										store.selectedRuleIds.length >= MAX_FINALISTS}
									onCheckedChange={() => store.toggleFinalist(candidate.id)}
								/>
								<Label for="finalist-{candidate.id}" class="cursor-pointer font-normal"
									>{candidate.name}</Label
								>
							</li>
						{/each}
					</ul>
					<p class="type-caption text-pretty text-ink-muted">
						Freezing records the rules, their parameters and the cost settings under a hash in the
						ledger. It cannot be undone, and only one freeze is allowed per dataset.
					</p>
					<div>
						<Button
							type="button"
							variant="secondary"
							disabled={!store.canFreeze}
							onclick={() => store.freeze()}
						>
							{#if store.freezeStatus === 'loading'}<LoaderCircle
									class="animate-spin"
									aria-hidden="true"
								/>
								Freezing&hellip;{:else}<Snowflake aria-hidden="true" /> Freeze selected rules{/if}
						</Button>
					</div>
				</fieldset>
			{:else}
				<div class="grid gap-3" data-testid="frozen">
					<p class="type-body-sm">
						Frozen {utc(freeze.frozen_at)}:
						<strong class="font-medium">{freeze.rules.map((r) => r.name).join(', ')}</strong>
					</p>
					<p class="type-micro break-all text-ink-muted">
						Hash <span class="font-mono">{freeze.hash}</span>
					</p>
				</div>
				{#if holdout.status === 'unread'}
					<div class="grid gap-3 rounded-lg bg-canvas p-[15px]" data-testid="read-holdout">
						<p class="type-body-sm text-pretty">
							Reading the holdout is a one-way step. With about {count(holdout.bars)} bars it is a sanity
							check, not a verdict, and looking again with a different rule set would turn it into training
							data, so the backend refuses a second read.
						</p>
						<div class="flex items-center gap-2.5">
							<Checkbox id="understood" bind:checked={understood} />
							<Label for="understood" class="cursor-pointer font-normal"
								>I understand this can be done once and cannot be undone</Label
							>
						</div>
						<div>
							<Button
								type="button"
								disabled={!understood || !store.canRead}
								onclick={() => store.readHoldout()}
							>
								{#if store.readStatus === 'loading'}<LoaderCircle
										class="animate-spin"
										aria-hidden="true"
									/>
									Reading&hellip;{:else}Read the holdout once{/if}
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</div>

		{#if freeze}
			<div
				class="grid grid-cols-[minmax(0,1fr)] gap-3 rounded-xl bg-surface-1 p-5"
				data-testid="forward-section"
			>
				<div class="grid gap-1">
					<h3 class="type-body-sm">Bars captured since the freeze</h3>
					<p class="max-w-[72ch] type-caption text-pretty text-ink-muted">
						The frozen rules, evaluated only on bars that arrived after they were frozen. This is
						the real out-of-sample record, and it grows as your capture runs.
					</p>
				</div>
				<div>
					<Button
						type="button"
						variant="secondary"
						disabled={store.forwardStatus === 'loading'}
						onclick={() => store.loadForward()}
					>
						{#if store.forwardStatus === 'loading'}<LoaderCircle
								class="animate-spin"
								aria-hidden="true"
							/>
							Checking&hellip;{:else}Check new bars{/if}
					</Button>
				</div>
				{#if store.forwardError}
					<p class="type-caption text-coral-ink" role="alert">{store.forwardError.message}</p>
				{:else if store.forward}
					{#if store.forward.waiting}
						<p class="type-body-sm text-ink-muted" data-testid="forward-waiting">
							No bars have been captured since the freeze ({utc(store.forward.start)}). Keep
							capturing and check again.
						</p>
					{:else}
						<p class="max-w-[72ch] type-caption text-pretty text-ink-muted">
							{store.forward.caveat}
						</p>
						<WindowTable
							rules={store.forward.rules}
							label="Frozen rules on bars since the freeze"
						/>
					{/if}
				{/if}
			</div>
		{/if}
	</section>
{/if}
