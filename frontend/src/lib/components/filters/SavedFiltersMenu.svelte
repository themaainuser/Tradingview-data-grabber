<script lang="ts">
	import Bookmark from '@lucide/svelte/icons/bookmark';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import * as Popover from '$lib/components/ui/popover';
	import { Button, buttonVariants } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { cloneWithNewIds } from '$lib/filters/tree';
	import type { FilterGroup } from '$lib/filters/types';
	import type { SavedFilters } from '$lib/state/saved-filters.svelte';
	import { cn } from '$lib/utils';

	interface Props {
		saved: SavedFilters;
		/** Current tree; saved as a snapshot. */
		tree: FilterGroup;
		canSave: boolean;
		onload: (tree: FilterGroup) => void;
	}

	let { saved, tree, canSave, onload }: Props = $props();
	let name = $state('');

	function save(event: SubmitEvent) {
		event.preventDefault();
		if (saved.save(name, $state.snapshot(tree) as FilterGroup)) name = '';
	}
</script>

<Popover.Root>
	<Popover.Trigger class={cn(buttonVariants({ variant: 'translucent', size: 'sm' }))}>
		<Bookmark aria-hidden="true" /> Saved
		<span class="text-ink-muted tabular-nums">{saved.items.length}</span>
	</Popover.Trigger>
	<Popover.Content class="w-80" align="end">
		<form class="flex gap-2" onsubmit={save}>
			<Input
				bind:value={name}
				placeholder="Name this filter"
				aria-label="Filter name"
				class="h-8"
			/>
			<Button type="submit" size="sm" disabled={!canSave || !name.trim()}>Save</Button>
		</form>
		{#if saved.persistError}
			<p class="type-caption text-coral-ink" role="alert">{saved.persistError}</p>
		{/if}
		{#if saved.items.length === 0}
			<p class="type-body-sm text-pretty text-ink-muted">
				Saved filters appear here. They stay in this browser only.
			</p>
		{:else}
			<ul class="grid grid-cols-[minmax(0,1fr)] gap-1">
				{#each saved.items as item (item.id)}
					<li class="flex items-center gap-1">
						<Button
							variant="ghost"
							size="sm"
							class="min-w-0 flex-1 justify-start"
							onclick={() => onload(cloneWithNewIds(item.tree))}
						>
							<span class="truncate">{item.name}</span>
						</Button>
						<Button
							variant="ghost"
							size="icon-sm"
							aria-label="Delete {item.name}"
							onclick={() => saved.remove(item.id)}
						>
							<Trash2 aria-hidden="true" />
						</Button>
					</li>
				{/each}
			</ul>
		{/if}
	</Popover.Content>
</Popover.Root>
