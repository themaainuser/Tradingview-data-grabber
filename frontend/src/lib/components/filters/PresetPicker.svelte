<script lang="ts">
	import Library from '@lucide/svelte/icons/library';
	import * as Popover from '$lib/components/ui/popover';
	import * as Command from '$lib/components/ui/command';
	import { buttonVariants } from '$lib/components/ui/button';
	import { groupBy } from '$lib/group';
	import type { FilterPreset } from '$lib/explorer/presets';
	import type { Condition } from '$lib/filters/types';
	import { cn } from '$lib/utils';

	interface Props {
		presets: readonly FilterPreset[];
		onpick: (conditions: Condition[]) => void;
	}

	let { presets, onpick }: Props = $props();

	let open = $state(false);
	let query = $state('');
	const LIMIT = 60;

	const results = $derived.by(() => {
		const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
		const hits = terms.length
			? presets.filter((p) => terms.every((t) => p.haystack.includes(t)))
			: presets;
		const shown = hits.slice(0, LIMIT);
		return { groups: groupBy(shown, (p) => p.group), total: hits.length, shown: shown.length };
	});

	function pick(preset: FilterPreset) {
		onpick(preset.build());
		open = false;
		query = '';
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger class={cn(buttonVariants({ variant: 'translucent', size: 'sm' }))}>
		<Library aria-hidden="true" /> Presets
		<span class="text-ink-muted tabular-nums">{presets.length}</span>
	</Popover.Trigger>
	<Popover.Content class="w-96 gap-0 p-1.5" align="end">
		<Command.Root shouldFilter={false}>
			<Command.Input
				placeholder="Search {presets.length} presets, e.g. “rsi cross”…"
				bind:value={query}
			/>
			<Command.List class="max-h-80">
				<Command.Empty>No preset matches “{query}”.</Command.Empty>
				{#each results.groups as [group, items] (group)}
					<Command.Group heading={group}>
						{#each items as preset (preset.id)}
							<Command.Item value={preset.id} onSelect={() => pick(preset)}>
								<span class="truncate">{preset.label}</span>
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
