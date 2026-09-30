<script lang="ts">
	import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
	import Check from '@lucide/svelte/icons/check';
	import * as Popover from '$lib/components/ui/popover';
	import * as Command from '$lib/components/ui/command';
	import type { FilterCatalog } from '$lib/filters/catalog';
	import { groupBy } from '$lib/group';
	import { cn } from '$lib/utils';

	interface Props {
		catalog: FilterCatalog;
		/** Selected field key, or '' when nothing is chosen. */
		value: string;
		onchange: (key: string) => void;
		placeholder?: string;
		/** Restrict to numeric fields (used for the right-hand side of comparisons). */
		numericOnly?: boolean;
		class?: string;
		label?: string;
	}

	let {
		catalog,
		value,
		onchange,
		placeholder = 'Choose field',
		numericOnly = false,
		class: className,
		label = 'Field'
	}: Props = $props();

	let open = $state(false);
	let query = $state('');

	// Rendering every option would put hundreds of nodes in the DOM; show the best matches only.
	const LIMIT = 60;

	const pool = $derived(
		numericOnly
			? catalog.options.filter((o) => catalog.kindOf(o.key) === 'numeric')
			: catalog.options
	);

	const results = $derived.by(() => {
		const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
		const hits = terms.length
			? pool.filter((o) => terms.every((t) => o.haystack.includes(t)))
			: pool;
		const shown = hits.slice(0, LIMIT);
		return { groups: groupBy(shown, (o) => o.group), total: hits.length, shown: shown.length };
	});

	function choose(key: string) {
		onchange(key);
		open = false;
		query = '';
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger
		class={cn(
			'inline-flex h-8 min-w-0 items-center justify-between gap-2 rounded-md border border-hairline bg-surface-1 px-3 type-body-sm text-ink transition-[border-color,background-color] duration-150 ease-out outline-none hover:bg-canvas focus-visible:border-accent-blue',
			className
		)}
		aria-label={label}
	>
		<span class={cn('truncate', !value && 'text-ink-muted')}>
			{value ? catalog.label(value) : placeholder}
		</span>
		<ChevronsUpDown class="size-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
	</Popover.Trigger>
	<Popover.Content class="w-80 gap-0 p-1.5" align="start">
		<Command.Root shouldFilter={false}>
			<Command.Input placeholder="Search {pool.length} fields…" bind:value={query} />
			<Command.List class="max-h-72">
				<Command.Empty>No field matches “{query}”.</Command.Empty>
				{#each results.groups as [group, options] (group)}
					<Command.Group heading={group}>
						{#each options as option (option.key)}
							<Command.Item
								value={option.key}
								onSelect={() => choose(option.key)}
								title={option.description}
							>
								<Check
									class={cn('size-3.5', option.key === value ? 'opacity-100' : 'opacity-0')}
									aria-hidden="true"
								/>
								<span class="truncate">{option.label}</span>
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
