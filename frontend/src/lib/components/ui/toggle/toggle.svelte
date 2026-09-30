<script lang="ts" module>
	import { type VariantProps, tv } from 'tailwind-variants';

	/** pricing-tab: default = canvas + muted, selected = one surface step up + ink (selected is lift, not colour). */
	export const toggleVariants = tv({
		base: "type-button group/toggle inline-flex shrink-0 items-center justify-center gap-1.5 rounded-pill bg-transparent text-ink-muted outline-none transition-[color,background-color,scale] duration-150 ease-out hover:text-ink active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40 data-[state=on]:bg-surface-2 data-[state=on]:text-ink [&_svg:not([class*='size-'])]:size-4",
		variants: {
			size: {
				default: 'px-[14px] py-[8px] pointer-coarse:min-h-11',
				sm: 'px-[12px] py-[6px] text-[13px] pointer-coarse:min-h-11'
			}
		},
		defaultVariants: {
			size: 'default'
		}
	});

	export type ToggleSize = VariantProps<typeof toggleVariants>['size'];
	export type ToggleVariants = VariantProps<typeof toggleVariants>;
</script>

<script lang="ts">
	import { Toggle as TogglePrimitive } from 'bits-ui';
	import { cn } from '$lib/utils.js';

	let {
		ref = $bindable(null),
		pressed = $bindable(false),
		class: className,
		size = 'default',
		...restProps
	}: TogglePrimitive.RootProps & {
		size?: ToggleSize;
	} = $props();
</script>

<TogglePrimitive.Root
	bind:ref
	bind:pressed
	data-slot="toggle"
	class={cn(toggleVariants({ size }), className)}
	{...restProps}
/>
