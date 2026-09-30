<script lang="ts">
	import { cn, type WithElementRef } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	/** `default` = pricing-card (surface-1); `featured` = pricing-card-featured (one surface step up). */
	let {
		ref = $bindable(null),
		class: className,
		children,
		variant = 'default',
		...restProps
	}: WithElementRef<HTMLAttributes<HTMLDivElement>> & {
		variant?: 'default' | 'featured';
	} = $props();
</script>

<div
	bind:this={ref}
	data-slot="card"
	data-variant={variant}
	class={cn(
		'flex flex-col gap-[15px] rounded-xl p-5 text-ink',
		variant === 'featured' ? 'bg-surface-2' : 'bg-surface-1',
		className
	)}
	{...restProps}
>
	{@render children?.()}
</div>
