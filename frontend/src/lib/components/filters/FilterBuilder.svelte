<script lang="ts">
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Alert from '$lib/components/ui/alert';
	import FilterGroupView from './FilterGroupView.svelte';
	import PresetPicker from './PresetPicker.svelte';
	import SavedFiltersMenu from './SavedFiltersMenu.svelte';
	import { countActive, describeNode, usesLookahead } from '$lib/filters/tree';
	import type { FilterCatalog } from '$lib/filters/catalog';
	import type { FilterEditor } from '$lib/filters/edit';
	import type { EvaluationResult, FilterGroup } from '$lib/filters/types';
	import type { SavedFilters } from '$lib/state/saved-filters.svelte';

	interface Props {
		tree: FilterGroup;
		editor: FilterEditor;
		catalog: FilterCatalog;
		evaluation: EvaluationResult | null;
		saved: SavedFilters;
		/** Noun for the rows being filtered, e.g. "bars" or "strategies". */
		unit: string;
	}

	let { tree, editor, catalog, evaluation, saved, unit }: Props = $props();

	const active = $derived(countActive(tree));
	const issues = $derived(new Map((evaluation?.issues ?? []).map((i) => [i.nodeId, i.message])));
	const summary = $derived(describeNode(tree, catalog.label));
	const lookahead = $derived(usesLookahead(tree));
</script>

<section class="grid grid-cols-[minmax(0,1fr)] gap-3" aria-label="Filters">
	<header class="flex flex-wrap items-center gap-2">
		<h2 class="type-body-sm">Filters</h2>
		<Badge variant="secondary" class="tabular-nums" data-testid="filter-count"
			>{active} active</Badge
		>
		{#if evaluation}
			<span
				class="type-caption text-ink-muted tabular-nums"
				data-testid="filter-matched"
				aria-live="polite"
			>
				{evaluation.matched.toLocaleString('en-US')} of {evaluation.total.toLocaleString('en-US')}
				{unit}
			</span>
		{/if}
		<div class="ml-auto flex flex-wrap items-center justify-end gap-1.5">
			{#if catalog.presets}
				<PresetPicker
					presets={catalog.presets}
					onpick={(conditions) => {
						for (const condition of conditions) editor.add(tree.id, condition);
					}}
				/>
			{/if}
			<SavedFiltersMenu {saved} {tree} canSave={active > 0} onload={editor.replace} />
			<Button variant="ghost" size="sm" disabled={tree.children.length === 0} onclick={editor.reset}
				>Clear</Button
			>
		</div>
	</header>

	<FilterGroupView group={tree} {catalog} {editor} {issues} root />

	{#if summary}
		<p
			class="border-t border-hairline pt-3 type-micro text-pretty text-ink-muted"
			data-testid="filter-summary"
		>
			{summary}
		</p>
	{/if}

	{#if lookahead}
		<Alert.Root class="bg-surface-2">
			<TriangleAlert aria-hidden="true" />
			<Alert.Title>Full-sample percentile in use</Alert.Title>
			<Alert.Description>
				Top/bottom-percent conditions rank each value against the entire dataset, including bars
				that come later. Use them to describe the data, not to test a tradeable rule.
			</Alert.Description>
		</Alert.Root>
	{/if}
</section>
