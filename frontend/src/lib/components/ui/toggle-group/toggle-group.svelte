<script lang="ts" module>
	import { getContext, setContext } from 'svelte';
	import { type ToggleSize } from '$lib/components/ui/toggle/index.js';

	interface ToggleGroupContext {
		size?: ToggleSize;
	}

	export function setToggleGroupCtx(props: ToggleGroupContext) {
		setContext('toggleGroup', props);
	}

	export function getToggleGroupCtx() {
		return getContext<ToggleGroupContext>('toggleGroup');
	}
</script>

<script lang="ts">
	import { ToggleGroup as ToggleGroupPrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		value = $bindable(),
		class: className,
		size = 'default',
		...restProps
	}: ToggleGroupPrimitive.RootProps & {
		size?: ToggleSize;
	} = $props();

	setToggleGroupCtx({
		get size() {
			return size;
		}
	});
</script>

<!--
Discriminated Unions + Destructing (required for bindable) do not
get along, so we shut typescript up by casting `value` to `never`.
-->
<ToggleGroupPrimitive.Root
	bind:value={value as never}
	bind:ref
	data-slot="toggle-group"
	class={cn('inline-flex w-fit items-center gap-0.5 rounded-pill bg-canvas p-0.5', className)}
	{...restProps}
/>
