<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Switch } from '$lib/components/ui/switch';
	import * as Select from '$lib/components/ui/select';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import type { AccountConfig } from '$lib/api/trading';
	import type { TradingStore } from '$lib/state/trading.svelte';
	import ConfirmAction from './ConfirmAction.svelte';
	import Field from './Field.svelte';

	let { store }: { store: TradingStore } = $props();

	onMount(() => {
		void store.loadConfig();
	});

	const SWITCHES = [
		{
			key: 'suspend_trade',
			label: 'Suspend trading',
			help: 'Blocks every new order until you turn it off again.'
		},
		{ key: 'no_shorting', label: 'Long only', help: 'Refuses orders that would sell short.' },
		{
			key: 'fractional_trading',
			label: 'Fractional shares',
			help: 'Allows quantities such as 0.5 shares.'
		},
		{
			key: 'disable_overnight_trading',
			label: 'No overnight trading',
			help: 'Keeps orders out of the overnight session.'
		},
		{
			key: 'ptp_no_exception_entry',
			label: 'Accept PTP orders with no exception',
			help: 'Publicly traded partnerships have tax rules; leave off unless you know them.'
		}
	] as const;

	let edited = $state<Partial<AccountConfig>>({});
	const saved = $derived(store.config.data);
	const current = $derived(saved ? { ...saved, ...edited } : null);
	const changed = $derived(
		saved
			? (Object.keys(edited) as (keyof AccountConfig)[]).filter((k) => edited[k] !== saved[k])
			: []
	);

	function set<K extends keyof AccountConfig>(key: K, value: AccountConfig[K]) {
		edited = { ...edited, [key]: value };
	}

	async function save() {
		const body = Object.fromEntries(changed.map((k) => [k, edited[k]]));
		const result = await store.updateConfig(body);
		if (result.ok) edited = {};
	}
</script>

<SectionCard
	id="settings"
	title="Account settings"
	description="These are kept by Alpaca and apply to every way you trade, not only this page."
>
	{#if store.config.problem && !saved}
		<p class="type-body-sm text-coral-ink" role="alert">{store.config.problem}</p>
	{:else if !current}
		<Skeleton class="h-40 w-full rounded-lg" />
	{:else}
		<div class="grid gap-5" data-testid="settings">
			<div class="grid gap-3 md:grid-cols-2">
				{#each SWITCHES as s (s.key)}
					<div class="flex items-start gap-3 rounded-lg bg-canvas p-3">
						<Switch
							id="setting-{s.key}"
							checked={current[s.key] === true}
							onCheckedChange={(v) => set(s.key, v)}
							aria-describedby="setting-{s.key}-help"
						/>
						<div class="grid gap-0.5">
							<label for="setting-{s.key}" class="type-body-sm font-medium">{s.label}</label>
							<p id="setting-{s.key}-help" class="type-caption text-pretty text-ink-muted">
								{s.help}
							</p>
						</div>
					</div>
				{/each}
			</div>
			<div class="grid gap-4 md:grid-cols-3">
				<Field
					id="setting-email"
					label="Email for fills"
					hint="Whether Alpaca emails you when an order fills."
				>
					<Select.Root
						type="single"
						value={current.trade_confirm_email ?? 'all'}
						onValueChange={(v) => v && set('trade_confirm_email', v)}
					>
						<Select.Trigger id="setting-email" class="w-full"
							>{current.trade_confirm_email === 'none' ? 'None' : 'Every fill'}</Select.Trigger
						>
						<Select.Content
							><Select.Item value="all" label="Every fill">Every fill</Select.Item><Select.Item
								value="none"
								label="None">None</Select.Item
							></Select.Content
						>
					</Select.Root>
				</Field>
				<Field
					id="setting-margin"
					label="Margin multiplier"
					hint="1 is cash only, 2 standard margin, 4 day-trading margin."
				>
					<Select.Root
						type="single"
						value={current.max_margin_multiplier ?? '2'}
						onValueChange={(v) => v && set('max_margin_multiplier', v)}
					>
						<Select.Trigger id="setting-margin" class="w-full"
							>{current.max_margin_multiplier ?? '—'}×</Select.Trigger
						>
						<Select.Content
							>{#each ['1', '2', '4'] as m (m)}<Select.Item value={m} label="{m}×">{m}×</Select.Item
								>{/each}</Select.Content
						>
					</Select.Root>
				</Field>
				<Field
					id="setting-level"
					label="Option trading level"
					hint="0 off, 1 covered calls and cash-secured puts, 2 long calls and puts, 3 spreads."
				>
					<Select.Root
						type="single"
						value={String(current.max_options_trading_level ?? 0)}
						onValueChange={(v) => v && set('max_options_trading_level', Number(v))}
					>
						<Select.Trigger id="setting-level" class="w-full"
							>Level {current.max_options_trading_level ?? '—'}</Select.Trigger
						>
						<Select.Content
							>{#each [0, 1, 2, 3] as level (level)}<Select.Item
									value={String(level)}
									label="Level {level}">Level {level}</Select.Item
								>{/each}</Select.Content
						>
					</Select.Root>
				</Field>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				{#if store.realMoney}
					<ConfirmAction
						label="Save settings"
						confirmLabel="Save to the live account"
						description="This changes the settings of your live account: {changed.join(', ')}."
						realMoney={true}
						variant="secondary"
						disabled={changed.length === 0 || store.busy > 0}
						onconfirm={save}
					/>
				{:else}
					<Button type="button" disabled={changed.length === 0 || store.busy > 0} onclick={save}
						>Save settings</Button
					>
				{/if}
				<Button
					type="button"
					variant="ghost"
					disabled={changed.length === 0}
					onclick={() => (edited = {})}>Discard changes</Button
				>
				<span class="type-caption text-ink-muted" aria-live="polite"
					>{changed.length === 0
						? 'No unsaved changes.'
						: `${changed.length} unsaved change${changed.length === 1 ? '' : 's'}.`}</span
				>
			</div>
		</div>
	{/if}
</SectionCard>
