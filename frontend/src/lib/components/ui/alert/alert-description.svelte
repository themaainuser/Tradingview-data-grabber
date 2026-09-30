<script lang="ts">
	import { cn, type WithElementRef } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: WithElementRef<HTMLAttributes<HTMLDivElement>> = $props();
</script>

<div
	bind:this={ref}
	data-slot="alert-description"
	class={cn(
		'type-body text-ink-muted group-has-[>svg]/alert:col-start-2 [&_a]:text-accent-blue [&_a]:hover:underline [&_p:not(:last-child)]:mb-3',
		className
	)}
	{...restProps}
>
	{@render children?.()}
</div>
