<script lang="ts" module>
	export type Side = 'top' | 'right' | 'bottom' | 'left';
</script>

<script lang="ts">
	import { Dialog as SheetPrimitive } from 'bits-ui';
	import XIcon from '@lucide/svelte/icons/x';
	import { Button } from '$lib/components/ui/button/index.js';
	import { cn, type WithoutChildrenOrChild } from '$lib/utils.js';
	import SheetOverlay from './sheet-overlay.svelte';
	import SheetPortal from './sheet-portal.svelte';
	import type { Snippet } from 'svelte';
	import type { ComponentProps } from 'svelte';

	let {
		ref = $bindable(null),
		class: className,
		side = 'right',
		showCloseButton = true,
		portalProps,
		children,
		...restProps
	}: WithoutChildrenOrChild<SheetPrimitive.ContentProps> & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof SheetPortal>>;
		side?: Side;
		showCloseButton?: boolean;
		children: Snippet;
	} = $props();
</script>

<SheetPortal {...portalProps}>
	<SheetOverlay />
	<SheetPrimitive.Content
		bind:ref
		data-slot="sheet-content"
		data-side={side}
		class={cn(
			'fixed z-50 flex flex-col gap-4 bg-canvas type-body text-ink shadow-float duration-200 ease-out data-closed:animate-out data-closed:fade-out-0 data-open:animate-in data-open:fade-in-0 data-[side=bottom]:inset-x-0 data-[side=bottom]:bottom-0 data-[side=bottom]:rounded-t-xl data-[side=bottom]:data-closed:slide-out-to-bottom-4 data-[side=bottom]:data-open:slide-in-from-bottom-4 data-[side=left]:inset-y-0 data-[side=left]:left-0 data-[side=left]:w-3/4 data-[side=left]:max-w-sm data-[side=left]:rounded-r-xl data-[side=left]:data-closed:slide-out-to-left-4 data-[side=left]:data-open:slide-in-from-left-4 data-[side=right]:inset-y-0 data-[side=right]:right-0 data-[side=right]:w-3/4 data-[side=right]:max-w-sm data-[side=right]:rounded-l-xl data-[side=right]:data-closed:slide-out-to-right-4 data-[side=right]:data-open:slide-in-from-right-4 data-[side=top]:inset-x-0 data-[side=top]:top-0 data-[side=top]:rounded-b-xl data-[side=top]:data-closed:slide-out-to-top-4 data-[side=top]:data-open:slide-in-from-top-4',
			className
		)}
		{...restProps}
	>
		{@render children?.()}
		{#if showCloseButton}
			<SheetPrimitive.Close data-slot="sheet-close">
				{#snippet child({ props })}
					<Button
						variant="secondary"
						class="absolute top-[12px] right-[15px]"
						size="icon-sm"
						{...props}
					>
						<XIcon />
						<span class="sr-only">Close</span>
					</Button>
				{/snippet}
			</SheetPrimitive.Close>
		{/if}
	</SheetPrimitive.Content>
</SheetPortal>
