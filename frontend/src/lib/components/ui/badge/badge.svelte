<script lang="ts" module>
	import { type VariantProps, tv } from 'tailwind-variants';

	/** Inline tag (DESIGN.md rounded.sm): a lifted surface with muted or ink text. */
	export const badgeVariants = tv({
		base: 'type-micro inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-sm px-[7px] py-[3px] whitespace-nowrap tabular-nums [&>svg]:size-3 [&>svg]:pointer-events-none',
		variants: {
			variant: {
				default: 'bg-surface-2 text-ink',
				secondary: 'bg-surface-2 text-ink-muted',
				success: 'bg-surface-2 text-success-ink',
				destructive: 'bg-surface-2 text-coral-ink'
			}
		},
		defaultVariants: {
			variant: 'default'
		}
	});

	export type BadgeVariant = VariantProps<typeof badgeVariants>['variant'];
</script>

<script lang="ts">
	import { cn, type WithElementRef } from '$lib/utils.js';
	import type { HTMLAnchorAttributes } from 'svelte/elements';

	let {
		ref = $bindable(null),
		href,
		class: className,
		variant = 'default',
		children,
		...restProps
	}: WithElementRef<HTMLAnchorAttributes> & {
		variant?: BadgeVariant;
	} = $props();
</script>

<svelte:element
	this={href ? 'a' : 'span'}
	bind:this={ref}
	data-slot="badge"
	{href}
	class={cn(badgeVariants({ variant }), className)}
	{...restProps}
>
	{@render children?.()}
</svelte:element>
