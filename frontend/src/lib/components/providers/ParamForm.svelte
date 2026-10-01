<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import X from '@lucide/svelte/icons/x';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Select from '$lib/components/ui/select';
	import type { CatalogParam } from '$lib/api/providers';
	import { describeParam, quotaText, visibleParams } from '$lib/providers/form';
	import type { ProvidersStore } from '$lib/state/providers.svelte';
	import PremiumBadge from './PremiumBadge.svelte';

	let { store }: { store: ProvidersStore } = $props();

	const NONE = '__none__';
	const endpoint = $derived(store.endpoint);
	const params = $derived(endpoint ? visibleParams(endpoint) : []);

	const single = (name: string) => {
		const value = store.values[name];
		return Array.isArray(value) ? (value[0] ?? '') : (value ?? '');
	};
	const entries = (name: string) => {
		const value = store.values[name];
		return Array.isArray(value) ? value : value ? [value] : [''];
	};
	const choices = (p: CatalogParam) => (p.type === 'boolean' ? ['true', 'false'] : p.enum);
	const choiceLabel = (p: CatalogParam, value: string) => p.enum_labels[value] ?? value;
	const fieldId = (name: string, index = 0) => `param-${store.endpointId}-${name}-${index}`;
	const placeholder = (p: CatalogParam) => (p.example ? `e.g. ${p.example}` : '');

	function setEntry(name: string, index: number, value: string) {
		const next = [...entries(name)];
		next[index] = value;
		store.setValue(name, next);
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		void store.fetch();
	}
</script>

{#if endpoint}
	<form
		class="grid grid-cols-[minmax(0,1fr)] gap-5"
		onsubmit={submit}
		aria-label="Request parameters"
		novalidate
	>
		{#if endpoint.examples.length > 0}
			<div class="grid gap-2">
				<p class="type-caption text-ink-muted">Fill from an example in the documentation</p>
				<div class="flex flex-wrap gap-2">
					{#each endpoint.examples as example, i (i)}
						<Button
							type="button"
							variant="translucent"
							size="xs"
							onclick={() => store.applyExample(i)}
							title={example.caption}
							class="h-auto max-w-full rounded-lg text-left whitespace-normal"
						>
							<span>{example.caption || `Example ${i + 1}`}</span>
						</Button>
					{/each}
				</div>
			</div>
		{/if}

		{#if params.length === 0}
			<p class="type-body-sm text-ink-muted">This endpoint takes no parameters.</p>
		{:else}
			<div class="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
				{#each params as p (p.name)}
					{@const error = store.errors[p.name]}
					{@const id = fieldId(p.name)}
					{@const about = describeParam(p)}
					<div
						class="grid content-start gap-1.5 {p.multiple || p.description.length > 140
							? 'md:col-span-2'
							: ''}"
					>
						<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
							<Label for={id} class="font-mono">{p.name}</Label>
							<span class="type-caption text-ink-muted">{p.required ? 'required' : 'optional'}</span
							>
							{#if p.premium_note}<PremiumBadge label="Premium option" />{/if}
						</div>

						{#if p.multiple}
							<div class="grid gap-2">
								{#each entries(p.name) as value, i (i)}
									<div class="flex items-center gap-2">
										<Input
											id={fieldId(p.name, i)}
											{value}
											oninput={(e) => setEntry(p.name, i, e.currentTarget.value)}
											placeholder={placeholder(p)}
											aria-invalid={error ? 'true' : undefined}
											aria-describedby="{id}-help"
											autocomplete="off"
											spellcheck="false"
										/>
										{#if entries(p.name).length > 1}
											<Button
												type="button"
												variant="ghost"
												size="icon-sm"
												aria-label="Remove {p.name} value {i + 1}"
												onclick={() => store.removeEntry(p.name, i)}
											>
												<X aria-hidden="true" />
											</Button>
										{/if}
									</div>
								{/each}
								<Button
									type="button"
									variant="translucent"
									size="xs"
									class="w-fit"
									onclick={() => store.addEntry(p.name)}
								>
									<Plus aria-hidden="true" /> Add {p.name} value
								</Button>
							</div>
						{:else if p.type === 'enum' || p.type === 'boolean'}
							<Select.Root
								type="single"
								value={single(p.name) || NONE}
								onValueChange={(v) => store.setValue(p.name, v === NONE ? '' : v)}
							>
								<Select.Trigger
									{id}
									class="w-full"
									aria-invalid={error ? 'true' : undefined}
									aria-describedby="{id}-help"
								>
									{single(p.name)
										? choiceLabel(p, single(p.name))
										: p.required
											? 'Choose…'
											: p.default
												? `Default (${p.default})`
												: 'Not set'}
								</Select.Trigger>
								<Select.Content>
									{#if !p.required}
										<Select.Item value={NONE} label="Not set"
											>{p.default ? `Default (${p.default})` : 'Not set'}</Select.Item
										>
									{/if}
									{#each choices(p) as value (value)}
										<Select.Item {value} label={choiceLabel(p, value)}>
											{choiceLabel(p, value)}
											{#if choiceLabel(p, value) !== value}
												<span class="ml-auto type-caption text-ink-muted">{value}</span>
											{/if}
											{#if p.premium_values.includes(value)}
												<PremiumBadge label="Premium" class="ml-auto" />
											{/if}
										</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						{:else}
							<Input
								{id}
								type={p.type === 'date' ? 'date' : p.type === 'month' ? 'month' : 'text'}
								inputmode={p.type === 'integer'
									? 'numeric'
									: p.type === 'number'
										? 'decimal'
										: undefined}
								value={single(p.name)}
								oninput={(e) => store.setValue(p.name, e.currentTarget.value)}
								placeholder={placeholder(p)}
								list={p.suggestions.length ? `${id}-list` : undefined}
								aria-invalid={error ? 'true' : undefined}
								aria-describedby="{id}-help"
								autocomplete="off"
								spellcheck="false"
							/>
							{#if p.suggestions.length}
								<datalist id="{id}-list">
									{#each p.suggestions as suggestion (suggestion)}<option value={suggestion}
										></option>{/each}
								</datalist>
							{/if}
						{/if}

						<div id="{id}-help" class="grid gap-1">
							{#if error}
								<p class="type-caption text-coral-ink" role="alert" data-testid="field-error">
									{error}
								</p>
							{/if}
							{#if about.text}
								<p class="type-caption text-pretty text-ink-muted">{about.text}</p>
							{/if}
							{#if about.premium}
								<p class="type-caption text-pretty text-orange-ink" data-testid="premium-note">
									Premium: {about.premium}
								</p>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}

		<div class="flex flex-wrap items-center gap-3">
			<Button type="submit" disabled={!store.canFetch} aria-describedby="fetch-help">
				{#if store.loading}<RefreshCw class="animate-spin" aria-hidden="true" /> Fetching…{:else}Fetch
					data{/if}
			</Button>
			<p id="fetch-help" class="type-caption text-ink-muted" data-testid="fetch-help">
				{#if store.blockedReason}
					{store.blockedReason}
				{:else}
					Uses {quotaText(store.requestCost)} from your {store.provider?.name} quota.
				{/if}
			</p>
		</div>
	</form>
{/if}
