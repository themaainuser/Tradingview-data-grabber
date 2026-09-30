<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import X from '@lucide/svelte/icons/x';
	import * as Popover from '$lib/components/ui/popover';
	import * as Command from '$lib/components/ui/command';
	import { Badge } from '$lib/components/ui/badge';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import ParamEditor from '$lib/components/filters/ParamEditor.svelte';
	import { getIndicator, INDICATORS, resolveParams } from '$lib/indicators';
	import { groupBy } from '$lib/group';
	import type { IndicatorDefinition } from '$lib/indicators/types';
	import type { ExplorerStore } from '$lib/state/explorer.svelte';
	import { cn } from '$lib/utils';

	interface Props {
		explorer: ExplorerStore;
	}

	let { explorer }: Props = $props();

	let open = $state(false);
	let query = $state('');
	const LIMIT = 60;

	const results = $derived.by(() => {
		const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
		const hits = terms.length
			? INDICATORS.filter((d) =>
					terms.every((t) => `${d.name} ${d.short} ${d.id} ${d.category}`.toLowerCase().includes(t))
				)
			: INDICATORS;
		const shown = hits.slice(0, LIMIT);
		return { groups: groupBy(shown, (d) => d.category), total: hits.length, shown: shown.length };
	});

	function add(definition: IndicatorDefinition) {
		explorer.addIndicator(definition.id);
		open = false;
		query = '';
	}
</script>

<section class="grid grid-cols-[minmax(0,1fr)] gap-3" aria-label="Chart indicators">
	<header class="flex items-center gap-2">
		<h2 class="type-body-sm">Indicators</h2>
		<Badge variant="secondary" class="tabular-nums">{explorer.indicators.length}</Badge>
		<Popover.Root bind:open>
			<Popover.Trigger
				class={cn(buttonVariants({ variant: 'translucent', size: 'sm' }), 'ml-auto')}
			>
				<Plus aria-hidden="true" /> Add
				<span class="text-ink-muted tabular-nums">{INDICATORS.length}</span>
			</Popover.Trigger>
			<Popover.Content class="w-96 gap-0 p-1.5" align="end">
				<Command.Root shouldFilter={false}>
					<Command.Input placeholder="Search {INDICATORS.length} indicators…" bind:value={query} />
					<Command.List class="max-h-80">
						<Command.Empty>No indicator matches “{query}”.</Command.Empty>
						{#each results.groups as [group, items] (group)}
							<Command.Group heading={group}>
								{#each items as definition (definition.id)}
									<Command.Item
										value={definition.id}
										onSelect={() => add(definition)}
										title={definition.description}
									>
										<span class="truncate">{definition.name}</span>
										<span class="ml-auto type-caption text-ink-muted"
											>{definition.pane === 'price' ? 'overlay' : 'pane'}</span
										>
									</Command.Item>
								{/each}
							</Command.Group>
						{/each}
						{#if results.total > results.shown}
							<p class="px-3 py-2 type-micro text-ink-muted">
								Showing {results.shown} of {results.total}. Keep typing to narrow.
							</p>
						{/if}
					</Command.List>
				</Command.Root>
			</Popover.Content>
		</Popover.Root>
	</header>

	{#if explorer.indicators.length === 0}
		<p class="type-body-sm text-pretty text-ink-muted">
			No indicators on the chart. Add one to overlay it on price or open its own pane.
		</p>
	{:else}
		<ul class="grid grid-cols-[minmax(0,1fr)] gap-1">
			{#each explorer.indicators as instance (instance.uid)}
				{@const definition = getIndicator(instance.id)}
				{#if definition}
					{@const values = resolveParams(definition, instance.params)}
					<li
						class="flex min-w-0 items-center gap-1.5 rounded-lg p-1.5 transition-colors duration-150 ease-out hover:bg-surface-2 {instance.visible
							? ''
							: 'opacity-50'}"
						data-testid="indicator-item"
					>
						<span
							class="size-2.5 shrink-0 rounded-full"
							style:background="var(--chart-{(instance.colorIndex % 5) + 1})"
							aria-hidden="true"
						></span>
						<div class="min-w-0 flex-1">
							<p class="truncate type-body-sm">{definition.name}</p>
							<p class="truncate type-caption text-ink-muted tabular-nums">
								{definition.pane === 'price' ? 'Overlay' : 'Own pane'}{definition.params.length
									? ' · '
									: ''}{definition.params.map((p) => `${p.label} ${values[p.key]}`).join(', ')}
							</p>
						</div>
						{#if definition.params.length}
							<ParamEditor
								specs={definition.params}
								{values}
								onchange={(next) => explorer.updateIndicator(instance.uid, next)}
								title={definition.name}
							/>
						{/if}
						<Button
							variant="ghost"
							size="icon-sm"
							aria-label={instance.visible ? `Hide ${definition.name}` : `Show ${definition.name}`}
							aria-pressed={instance.visible}
							onclick={() => explorer.toggleIndicator(instance.uid)}
						>
							{#if instance.visible}<Eye aria-hidden="true" />{:else}<EyeOff
									aria-hidden="true"
								/>{/if}
						</Button>
						<Button
							variant="ghost"
							size="icon-sm"
							aria-label="Remove {definition.name}"
							onclick={() => explorer.removeIndicator(instance.uid)}
						>
							<X aria-hidden="true" />
						</Button>
					</li>
				{/if}
			{/each}
		</ul>
	{/if}
</section>
