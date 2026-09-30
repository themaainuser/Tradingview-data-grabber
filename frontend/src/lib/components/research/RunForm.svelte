<script lang="ts">
	import Play from '@lucide/svelte/icons/play';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import type { DatasetsStore } from '$lib/state/datasets.svelte';
	import type { ResearchStore } from '$lib/state/research.svelte';

	interface Props {
		research: ResearchStore;
		datasets: DatasetsStore;
	}

	let { research, datasets }: Props = $props();

	// Conventional annualisation factors: labels for the number, not data.
	const PERIODS = [
		{ label: 'Daily (252)', value: 252 },
		{ label: 'Daily 24/7 (365)', value: 365 },
		{ label: 'Hourly 24/7', value: 8760 },
		{ label: '5-min 24/7', value: 105_120 }
	];

	const running = $derived(research.status === 'loading');
</script>

<form
	class="grid gap-5"
	onsubmit={(e) => {
		e.preventDefault();
		research.run();
	}}
	aria-label="Research run parameters"
>
	<fieldset class="grid gap-2">
		<legend class="mb-1 type-body-sm">Datasets</legend>
		{#if datasets.usable.length === 0}
			<p class="type-body-sm text-pretty text-ink-muted">
				{datasets.status === 'loading'
					? 'Loading datasets…'
					: 'No usable datasets on the backend. Capture bars first; imported CSVs cannot be sent to the backend.'}
			</p>
		{:else}
			<ul class="grid max-h-56 grid-cols-[minmax(0,1fr)] gap-1 overflow-y-auto pr-1">
				{#each datasets.usable as dataset (dataset.id)}
					<li class="flex items-center gap-2">
						<Checkbox
							id="ds-{dataset.id}"
							checked={research.selectedIds.includes(dataset.id)}
							onCheckedChange={() => research.toggleDataset(dataset.id)}
						/>
						<Label
							for="ds-{dataset.id}"
							class="min-w-0 flex-1 cursor-pointer justify-between gap-2 font-normal"
						>
							<span class="truncate"
								>{dataset.symbol}{dataset.timeframe ? ` · ${dataset.timeframe}` : ''}</span
							>
							<span class="type-caption text-ink-muted tabular-nums"
								>{dataset.rows.toLocaleString('en-US')}</span
							>
						</Label>
					</li>
				{/each}
			</ul>
		{/if}
		{#if research.validation.datasets && datasets.usable.length > 0}
			<p class="type-caption text-ink-muted">{research.validation.datasets}</p>
		{/if}
	</fieldset>

	<div class="grid gap-1.5">
		<Label for="fee">Cost per position change (bps)</Label>
		<Input
			id="fee"
			type="number"
			min="0"
			max="10000"
			step="any"
			class="tabular-nums"
			bind:value={research.feeBps}
			aria-invalid={research.validation.feeBps !== null}
		/>
		{#if research.validation.feeBps}<p class="type-caption text-coral-ink" role="alert">
				{research.validation.feeBps}
			</p>{/if}
	</div>

	<div class="grid gap-1.5">
		<Label for="ppy">Periods per year</Label>
		<Input
			id="ppy"
			type="number"
			min="0"
			step="any"
			class="tabular-nums"
			bind:value={research.periodsPerYear}
			aria-invalid={research.validation.periodsPerYear !== null}
		/>
		{#if research.validation.periodsPerYear}<p class="type-caption text-coral-ink" role="alert">
				{research.validation.periodsPerYear}
			</p>{/if}
		<div class="flex flex-wrap gap-1">
			{#each PERIODS as preset (preset.value)}
				<Button
					type="button"
					variant="translucent"
					size="xs"
					onclick={() => (research.periodsPerYear = preset.value)}>{preset.label}</Button
				>
			{/each}
		</div>
		<p class="type-caption text-pretty text-ink-muted">
			Sets Sharpe / CAGR annualisation. Match it to the bar interval and market hours.
		</p>
	</div>

	<div class="flex items-center gap-2">
		<Button type="submit" disabled={!research.canRun}>
			{#if running}<LoaderCircle class="animate-spin" aria-hidden="true" /> Running…{:else}<Play
					aria-hidden="true"
				/> Run research{/if}
		</Button>
		{#if running}
			<Button type="button" variant="ghost" onclick={() => research.cancel()}>Cancel</Button>
		{/if}
	</div>
</form>
