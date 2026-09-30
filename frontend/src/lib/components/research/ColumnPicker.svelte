<script lang="ts">
	import Columns3 from '@lucide/svelte/icons/columns-3';
	import * as Popover from '$lib/components/ui/popover';
	import { buttonVariants } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { groupBy } from '$lib/group';
	import type { ResearchColumn } from '$lib/research/columns';
	import { cn } from '$lib/utils';

	interface Props {
		columns: readonly ResearchColumn[];
		visible: readonly string[];
		ontoggle: (key: string) => void;
	}

	let { columns, visible, ontoggle }: Props = $props();
	let query = $state('');

	const groups = $derived.by(() => {
		const q = query.toLowerCase().trim();
		const matching = q
			? columns.filter((c) => `${c.group} ${c.label}`.toLowerCase().includes(q))
			: columns;
		return groupBy(matching, (c) => c.group);
	});
</script>

<Popover.Root>
	<Popover.Trigger class={cn(buttonVariants({ variant: 'translucent', size: 'sm' }))}>
		<Columns3 aria-hidden="true" /> Columns
		<span class="text-ink-muted tabular-nums">{visible.length}/{columns.length}</span>
	</Popover.Trigger>
	<Popover.Content class="w-80" align="end">
		<Input
			placeholder="Search columns…"
			bind:value={query}
			aria-label="Search columns"
			class="h-8"
		/>
		<div class="grid max-h-80 gap-3 overflow-y-auto pr-1">
			{#each groups as [group, items] (group)}
				<fieldset class="grid gap-1.5">
					<legend class="mb-1 type-caption font-medium text-ink-muted">{group}</legend>
					{#each items as column (column.key)}
						<div class="flex items-center gap-2">
							<Checkbox
								id="col-{column.key}"
								checked={visible.includes(column.key)}
								onCheckedChange={() => ontoggle(column.key)}
							/>
							<Label
								for="col-{column.key}"
								class="cursor-pointer font-normal"
								title={column.description}>{column.label}</Label
							>
						</div>
					{/each}
				</fieldset>
			{:else}
				<p class="type-body text-ink-muted">No column matches “{query}”.</p>
			{/each}
		</div>
	</Popover.Content>
</Popover.Root>
