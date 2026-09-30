<script lang="ts" module>
	import { type VariantProps, tv } from 'tailwind-variants';
	import { cn, type WithElementRef } from '$lib/utils.js';
	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';

	/**
	 * Pills are the only CTA shape (DESIGN.md): white primary, charcoal secondary, surface-2 translucent.
	 * There are no bordered ghost buttons. Press feedback is a 0.96 scale, not a darker fill.
	 */
	export const buttonVariants = tv({
		base: "type-button group/button inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap outline-none select-none transition-[color,background-color,opacity,scale] duration-150 ease-out active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40 aria-disabled:pointer-events-none aria-disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
		variants: {
			variant: {
				default: 'bg-primary text-on-primary hover:bg-primary/90',
				secondary: 'bg-surface-1 text-ink hover:bg-surface-2',
				translucent: 'bg-surface-2 text-ink hover:bg-surface-2/70',
				ghost: 'text-ink-muted hover:bg-white/10 hover:text-ink',
				destructive: 'bg-surface-1 text-gradient-coral hover:bg-surface-2',
				link: 'text-accent-blue underline-offset-4 hover:underline'
			},
			size: {
				// 10px 15px padding on a 14px line = the documented pill; touch pointers get the 44px target.
				default: 'rounded-pill px-[15px] py-[10px] pointer-coarse:min-h-11',
				sm: 'rounded-pill px-[14px] py-[8px] pointer-coarse:min-h-11',
				xs: 'rounded-pill px-[10px] py-[6px] text-[13px] pointer-coarse:min-h-11',
				lg: 'rounded-pill px-[20px] py-[14px]',
				icon: 'size-10 rounded-full pointer-coarse:size-11',
				'icon-sm': 'size-8 rounded-full pointer-coarse:size-11'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'default'
		}
	});

	export type ButtonVariant = VariantProps<typeof buttonVariants>['variant'];
	export type ButtonSize = VariantProps<typeof buttonVariants>['size'];

	export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
		WithElementRef<HTMLAnchorAttributes> & {
			variant?: ButtonVariant;
			size?: ButtonSize;
		};
</script>

<script lang="ts">
	let {
		class: className,
		variant = 'default',
		size = 'default',
		ref = $bindable(null),
		href = undefined,
		type = 'button',
		disabled,
		children,
		...restProps
	}: ButtonProps = $props();
</script>

{#if href}
	<a
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		href={disabled ? undefined : href}
		aria-disabled={disabled}
		role={disabled ? 'link' : undefined}
		tabindex={disabled ? -1 : undefined}
		{...restProps}
	>
		{@render children?.()}
	</a>
{:else}
	<button
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		{type}
		{disabled}
		{...restProps}
	>
		{@render children?.()}
	</button>
{/if}
