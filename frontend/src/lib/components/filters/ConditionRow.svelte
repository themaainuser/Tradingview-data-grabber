<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import Link2 from '@lucide/svelte/icons/link-2';
	import Hash from '@lucide/svelte/icons/hash';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import FieldPicker from './FieldPicker.svelte';
	import ParamEditor from './ParamEditor.svelte';
	import { getOperator, operatorsFor } from '$lib/filters/operators';
	import type { FilterCatalog } from '$lib/filters/catalog';
	import type { NodePatch } from '$lib/filters/edit';
	import type { Condition, Operator } from '$lib/filters/types';
	import { cn } from '$lib/utils';

	interface Props {
		node: Condition;
		catalog: FilterCatalog;
		/** Reason the condition cannot be evaluated, if any. */
		issue?: string;
		onpatch: (patch: NodePatch) => void;
		onremove: () => void;
	}

	let { node, catalog, issue, onpatch, onremove }: Props = $props();

	const kind = $derived(catalog.kindOf(node.field) ?? 'numeric');
	const operators = $derived(operatorsFor(kind, catalog.ordered));
	const spec = $derived(getOperator(node.op));
	const usesField = $derived(node.rhs !== null);
	const leftParams = $derived(node.field ? (catalog.params?.(node.field) ?? null) : null);
	const rightParams = $derived(node.rhs ? (catalog.params?.(node.rhs) ?? null) : null);

	function number(event: Event & { currentTarget: HTMLInputElement }): number {
		return event.currentTarget.valueAsNumber;
	}

	function changeField(field: string) {
		// Switching between numeric and text fields invalidates the operator; pick a sensible default.
		const nextKind = catalog.kindOf(field) ?? 'numeric';
		const allowed = operatorsFor(nextKind, catalog.ordered);
		const patch: NodePatch = { field };
		if (!allowed.some((o) => o.id === node.op)) {
			patch.op = allowed[0].id;
			patch.rhs = null;
		}
		onpatch(patch);
	}

	function changeOperator(op: Operator) {
		const next = getOperator(op);
		onpatch({ op, rhs: next.allowsField ? node.rhs : null });
	}

	function countStep(op: Operator): number {
		return op === 'top_pct' || op === 'bottom_pct' ? 0.5 : 1;
	}
</script>

<div class="grid gap-1">
	<div
		class={cn(
			'grid gap-2 rounded-lg bg-surface-2 p-[10px] transition-[opacity,box-shadow] duration-150 ease-out',
			issue && 'shadow-[0_0_0_1px_rgb(255_85_119/0.55)]',
			!node.enabled && 'opacity-50'
		)}
		data-testid="condition-row"
		data-invalid={issue ? 'true' : undefined}
	>
		<div class="flex items-center gap-1.5">
			<Checkbox
				checked={node.enabled}
				onCheckedChange={(checked) => onpatch({ enabled: checked === true })}
				aria-label="Enable condition"
			/>
			<FieldPicker
				{catalog}
				value={node.field}
				onchange={changeField}
				class="min-w-0 flex-1"
				label="Field"
			/>
			{#if leftParams}
				<ParamEditor
					specs={leftParams.specs}
					values={leftParams.values}
					onchange={(values) => onpatch({ field: leftParams.withParams(values) })}
					title={catalog.label(node.field)}
				/>
			{/if}
			<Button variant="ghost" size="icon-sm" aria-label="Remove condition" onclick={onremove}>
				<X aria-hidden="true" />
			</Button>
		</div>

		<div class="flex flex-wrap items-center gap-1.5 pl-6">
			<Select.Root
				type="single"
				value={node.op}
				onValueChange={(v) => changeOperator(v as Operator)}
			>
				<Select.Trigger size="sm" class="w-40" aria-label="Operator">
					{spec.label}
				</Select.Trigger>
				<Select.Content>
					{#each operators as option (option.id)}
						<Select.Item value={option.id} label={option.label}>{option.label}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>

			{#if spec.operand === 'value'}
				{#if usesField}
					<FieldPicker
						{catalog}
						value={node.rhs ?? ''}
						onchange={(rhs) => onpatch({ rhs })}
						numericOnly
						class="w-40"
						label="Compare with field"
					/>
					{#if rightParams}
						<ParamEditor
							specs={rightParams.specs}
							values={rightParams.values}
							onchange={(values) => onpatch({ rhs: rightParams.withParams(values) })}
							title={catalog.label(node.rhs ?? '')}
						/>
					{/if}
				{:else}
					<Input
						type="number"
						step="any"
						class="h-8 w-28 tabular-nums"
						value={node.value}
						oninput={(e) => onpatch({ value: number(e) })}
						aria-label="Value"
					/>
				{/if}
				{#if spec.allowsField}
					<Button
						variant="ghost"
						size="icon-sm"
						aria-label={usesField ? 'Compare with a number' : 'Compare with another field'}
						aria-pressed={usesField}
						onclick={() =>
							onpatch({
								rhs: usesField
									? null
									: (catalog.options.find((o) => catalog.kindOf(o.key) === 'numeric')?.key ?? null)
							})}
					>
						{#if usesField}<Hash aria-hidden="true" />{:else}<Link2 aria-hidden="true" />{/if}
					</Button>
				{/if}
			{:else if spec.operand === 'range'}
				<Input
					type="number"
					step="any"
					class="h-8 w-24 tabular-nums"
					value={node.value}
					oninput={(e) => onpatch({ value: number(e) })}
					aria-label="Lower bound"
				/>
				<span class="type-caption text-ink-muted">and</span>
				<Input
					type="number"
					step="any"
					class="h-8 w-24 tabular-nums"
					value={node.value2}
					oninput={(e) => onpatch({ value2: number(e) })}
					aria-label="Upper bound"
				/>
			{:else if spec.operand === 'count' || spec.operand === 'percent'}
				<Input
					type="number"
					min="0"
					step={countStep(node.op)}
					class="h-8 w-24 tabular-nums"
					value={node.value}
					oninput={(e) => onpatch({ value: number(e) })}
					aria-label={spec.operand === 'count' ? 'Number of bars' : 'Percent'}
				/>
				<span class="type-caption text-ink-muted">{spec.operand === 'count' ? 'bars' : '%'}</span>
			{:else if spec.operand === 'text'}
				<Input
					class="h-8 w-48"
					value={node.text}
					placeholder={node.op === 'in' || node.op === 'not_in' ? 'a, b, c' : 'text'}
					oninput={(e) => onpatch({ text: e.currentTarget.value })}
					aria-label="Text"
				/>
			{/if}
		</div>
	</div>
	{#if issue}
		<p class="px-2 type-caption text-gradient-coral" role="alert">{issue}</p>
	{/if}
</div>
