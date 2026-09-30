<script lang="ts">
	import { ToggleGroup as ToggleGroupPrimitive } from 'bits-ui';
	import { getToggleGroupCtx } from './toggle-group.svelte';
	import { cn } from '$lib/utils.js';
	import { toggleVariants, type ToggleSize } from '$lib/components/ui/toggle/index.js';

	let {
		ref = $bindable(null),
		value = $bindable(),
		class: className,
		size,
		...restProps
	}: ToggleGroupPrimitive.ItemProps & { size?: ToggleSize } = $props();

	const ctx = getToggleGroupCtx();
</script>

<ToggleGroupPrimitive.Item
	bind:ref
	data-slot="toggle-group-item"
	class={cn(toggleVariants({ size: ctx?.size || size }), className)}
	{value}
	{...restProps}
/>
