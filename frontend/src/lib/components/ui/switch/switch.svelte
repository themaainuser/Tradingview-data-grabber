<script lang="ts">
	import { Switch as SwitchPrimitive } from 'bits-ui';
	import { cn, type WithoutChildrenOrChild } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		class: className,
		checked = $bindable(false),
		...restProps
	}: WithoutChildrenOrChild<SwitchPrimitive.RootProps> = $props();
</script>

<SwitchPrimitive.Root
	bind:ref
	bind:checked
	data-slot="switch"
	class={cn(
		'peer relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full bg-ink-muted/30 p-[3px] transition-[background-color] duration-150 ease-out outline-none after:absolute after:-inset-2 disabled:cursor-not-allowed disabled:opacity-40 data-[state=checked]:bg-primary',
		className
	)}
	{...restProps}
>
	<SwitchPrimitive.Thumb
		data-slot="switch-thumb"
		class="pointer-events-none block size-4 rounded-full bg-ink transition-[translate,background-color] duration-150 ease-out data-[state=checked]:translate-x-4 data-[state=checked]:bg-on-primary"
	/>
</SwitchPrimitive.Root>
