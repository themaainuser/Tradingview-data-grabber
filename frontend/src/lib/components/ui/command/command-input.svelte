<script lang="ts">
	import { Command as CommandPrimitive } from 'bits-ui';
	import SearchIcon from '@lucide/svelte/icons/search';
	import { cn } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		class: className,
		value = $bindable(''),
		...restProps
	}: CommandPrimitive.InputProps = $props();
</script>

<div
	data-slot="command-input-wrapper"
	class="flex items-center gap-2 border-b border-hairline px-3 pb-2 transition-[border-color] duration-150 ease-out focus-within:border-accent-blue"
>
	<SearchIcon class="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
	<CommandPrimitive.Input
		bind:ref
		bind:value
		data-slot="command-input"
		class={cn(
			'h-8 w-full bg-transparent type-body text-ink outline-hidden placeholder:text-ink-muted focus-visible:shadow-none disabled:cursor-not-allowed disabled:opacity-40',
			className
		)}
		{...restProps}
	/>
</div>
