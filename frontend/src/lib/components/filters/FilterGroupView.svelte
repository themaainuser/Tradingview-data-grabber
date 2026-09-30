<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import FolderPlus from '@lucide/svelte/icons/folder-plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import { Toggle } from '$lib/components/ui/toggle';
	import ConditionRow from './ConditionRow.svelte';
	import FilterGroupView from './FilterGroupView.svelte';
	import { newCondition, newGroup } from '$lib/filters/tree';
	import type { FilterCatalog } from '$lib/filters/catalog';
	import type { FilterEditor } from '$lib/filters/edit';
	import type { FilterGroup, GroupMode } from '$lib/filters/types';

	interface Props {
		group: FilterGroup;
		catalog: FilterCatalog;
		editor: FilterEditor;
		/** Evaluation problems keyed by node id. */
		issues: ReadonlyMap<string, string>;
		root?: boolean;
	}

	let { group, catalog, editor, issues, root = false }: Props = $props();
</script>

<div
	class="grid gap-2 {root ? '' : 'rounded-lg bg-canvas p-[10px]'}"
	data-testid={root ? 'filter-root' : 'filter-group'}
>
	<div class="flex flex-wrap items-center gap-1.5">
		{#if !root}
			<Checkbox
				checked={group.enabled}
				onCheckedChange={(checked) => editor.patch(group.id, { enabled: checked === true })}
				aria-label="Enable group"
			/>
		{/if}
		<ToggleGroup.Root
			type="single"
			size="sm"
			class={root ? '' : 'bg-surface-1'}
			value={group.mode}
			onValueChange={(mode) => mode && editor.patch(group.id, { mode: mode as GroupMode })}
			aria-label="Combine conditions with"
		>
			<ToggleGroup.Item value="and" aria-label="All conditions must match">ALL</ToggleGroup.Item>
			<ToggleGroup.Item value="or" aria-label="Any condition may match">ANY</ToggleGroup.Item>
		</ToggleGroup.Root>
		<Toggle
			size="sm"
			pressed={group.negate}
			onPressedChange={(negate) => editor.patch(group.id, { negate })}
			aria-label="Negate group"
		>
			NOT
		</Toggle>
		<div class="ml-auto flex items-center gap-1">
			<Button variant="ghost" size="xs" onclick={() => editor.add(group.id, newCondition())}>
				<Plus aria-hidden="true" /> Condition
			</Button>
			<Button
				variant="ghost"
				size="xs"
				onclick={() =>
					editor.add(group.id, newGroup(group.mode === 'and' ? 'or' : 'and', [newCondition()]))}
			>
				<FolderPlus aria-hidden="true" /> Group
			</Button>
			{#if !root}
				<Button
					variant="ghost"
					size="icon-sm"
					aria-label="Remove group"
					onclick={() => editor.remove(group.id)}
				>
					<Trash2 aria-hidden="true" />
				</Button>
			{/if}
		</div>
	</div>

	{#each group.children as child (child.id)}
		{#if child.type === 'group'}
			<FilterGroupView group={child} {catalog} {editor} {issues} />
		{:else}
			<ConditionRow
				node={child}
				{catalog}
				issue={issues.get(child.id)}
				onpatch={(patch) => editor.patch(child.id, patch)}
				onremove={() => editor.remove(child.id)}
			/>
		{/if}
	{:else}
		{#if root}
			<p class="px-1 py-2 type-body text-pretty text-ink-muted">
				No conditions yet. Add one, or pick from the preset library.
			</p>
		{/if}
	{/each}
</div>
