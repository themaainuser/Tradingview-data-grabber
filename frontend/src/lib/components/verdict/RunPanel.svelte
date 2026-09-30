<script lang="ts">
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import Play from '@lucide/svelte/icons/play';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import type { VerdictStore } from '$lib/state/verdict.svelte';
	import { BOUNDS } from '$lib/verdict/form';
	import { count, pctOf, utc } from '$lib/verdict/present';

	interface Props {
		store: VerdictStore;
	}

	let { store }: Props = $props();

	const FRACTIONS = [0.1, 0.15, 0.2, 0.25, 0.3];
	const running = $derived(store.runStatus === 'loading');
	const holdout = $derived(store.state?.holdout ?? null);
	const notes = $derived(
		Object.fromEntries((store.state?.defaults.cost_notes ?? []).map((n) => [n.field, n.basis]))
	);
	const errors = $derived(store.errors);
</script>

<form
	class="grid gap-5"
	aria-label="Verdict settings"
	onsubmit={(e) => {
		e.preventDefault();
		store.run();
	}}
>
	<div class="grid gap-1.5">
		<Label for="min-trades">Minimum trades per rule</Label>
		<Input
			id="min-trades"
			type="number"
			min={BOUNDS.minTrades.min}
			max={BOUNDS.minTrades.max}
			step="1"
			class="tabular-nums"
			bind:value={store.form.minTrades}
			aria-invalid={errors.minTrades !== null}
			aria-describedby="min-trades-note"
		/>
		{#if errors.minTrades}<p class="type-caption text-coral-ink" role="alert">
				{errors.minTrades}
			</p>{/if}
		<p id="min-trades-note" class="type-caption text-pretty text-ink-muted">
			Rules below this get no statistics. 30 is the bare minimum for any statistic to mean
			something; 100 or more is much better.
		</p>
	</div>

	<fieldset class="grid gap-3">
		<legend class="mb-1 type-body-sm">Costs, charged on both sides of every trade</legend>
		<div class="grid gap-1.5">
			<Label for="fee">Fee (bps per side)</Label>
			<Input
				id="fee"
				type="number"
				min={BOUNDS.fee.min}
				max={BOUNDS.fee.max}
				step="any"
				class="tabular-nums"
				bind:value={store.form.fee}
				aria-invalid={errors.fee !== null}
				aria-describedby="fee-note"
			/>
			{#if errors.fee}<p class="type-caption text-coral-ink" role="alert">{errors.fee}</p>{/if}
			{#if notes.fee_bps_per_side}<p id="fee-note" class="type-caption text-pretty text-ink-muted">
					{notes.fee_bps_per_side}
				</p>{/if}
		</div>
		<div class="grid gap-1.5">
			<Label for="spread">Spread (bps, whole spread)</Label>
			<Input
				id="spread"
				type="number"
				min={BOUNDS.spread.min}
				max={BOUNDS.spread.max}
				step="any"
				class="tabular-nums"
				bind:value={store.form.spread}
				aria-invalid={errors.spread !== null}
				aria-describedby="spread-note"
			/>
			{#if errors.spread}<p class="type-caption text-coral-ink" role="alert">
					{errors.spread}
				</p>{/if}
			<p id="spread-note" class="type-caption text-pretty text-ink-muted">
				Half is charged per side. {notes.spread_bps ?? ''}
			</p>
		</div>
		<div class="grid gap-1.5">
			<Label for="slippage">Slippage (&times; ATR 14)</Label>
			<Input
				id="slippage"
				type="number"
				min={BOUNDS.slippageK.min}
				max={BOUNDS.slippageK.max}
				step="any"
				class="tabular-nums"
				bind:value={store.form.slippageK}
				aria-invalid={errors.slippageK !== null}
				aria-describedby="slippage-note"
			/>
			{#if errors.slippageK}<p class="type-caption text-coral-ink" role="alert">
					{errors.slippageK}
				</p>{/if}
			{#if notes.slippage_k}<p id="slippage-note" class="type-caption text-pretty text-ink-muted">
					{notes.slippage_k}
				</p>{/if}
		</div>
		<p class="type-caption text-pretty text-ink-muted">
			These are assumptions to check against your venue. Every rule is also run at 1.5&times; and
			2&times; these costs.
		</p>
	</fieldset>

	<div class="grid gap-1.5">
		<Label for="ppy">Periods per year</Label>
		<Input
			id="ppy"
			type="number"
			min="0"
			step="any"
			class="tabular-nums"
			placeholder="Inferred from bar spacing"
			bind:value={store.form.periodsPerYear}
			aria-invalid={errors.periodsPerYear !== null}
		/>
		{#if errors.periodsPerYear}<p class="type-caption text-coral-ink" role="alert">
				{errors.periodsPerYear}
			</p>{/if}
		<p class="type-caption text-pretty text-ink-muted">
			Annualises Sharpe. Leave empty to infer it assuming the market trades continuously.
		</p>
	</div>

	<fieldset class="grid gap-2" data-testid="holdout-setup">
		<legend class="mb-1 type-body-sm">Sealed holdout</legend>
		{#if holdout}
			<p class="type-caption text-pretty text-ink-muted tabular-nums">
				Sealed: the most recent {pctOf(holdout.fraction)} ({count(holdout.bars)} bars,
				{utc(holdout.start, false)} to {utc(holdout.end, false)}). No analysis on this page can see
				it.
			</p>
		{:else}
			<ToggleGroup.Root
				type="single"
				size="sm"
				value={String(store.form.holdoutFraction)}
				onValueChange={(v) => v && (store.form.holdoutFraction = Number(v))}
				aria-label="Share of the most recent bars to seal"
			>
				{#each FRACTIONS as fraction (fraction)}
					<ToggleGroup.Item value={String(fraction)}>{pctOf(fraction)}</ToggleGroup.Item>
				{/each}
			</ToggleGroup.Root>
			{#if errors.holdoutFraction}<p class="type-caption text-coral-ink" role="alert">
					{errors.holdoutFraction}
				</p>{/if}
			<p class="type-caption text-pretty text-ink-muted">
				The first run seals this share of the most recent bars before any analysis. It is excluded
				from every research query and can be read once, and only for a candidate.
			</p>
		{/if}
	</fieldset>

	<div class="grid gap-2">
		<Button type="submit" disabled={!store.canRun}>
			{#if running}<LoaderCircle class="animate-spin" aria-hidden="true" /> Running&hellip;{:else}<Play
					aria-hidden="true"
				/>
				{store.sealed ? 'Run verdict' : 'Seal holdout and run verdict'}{/if}
		</Button>
		{#if store.differs && !running}
			<p class="type-caption text-pretty text-ink-muted" data-testid="settings-changed">
				These settings differ from the verdict shown. Run again to update it.
			</p>
		{/if}
		{#if store.runError}
			<p class="type-caption text-pretty text-coral-ink" role="alert" data-testid="run-error">
				{store.runError.message}
			</p>
		{/if}
	</div>
</form>
