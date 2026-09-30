<script lang="ts">
	import type { Component } from 'svelte';
	import type { SVGAttributes } from 'svelte/elements';
	import * as Sheet from '$lib/components/ui/sheet';

	interface NavItem {
		href: string;
		label: string;
		icon: Component<SVGAttributes<SVGSVGElement>>;
	}

	interface Props {
		open: boolean;
		items: readonly NavItem[];
		isActive: (href: string) => boolean;
		status: { label: string; dot: string };
	}

	// Loaded on first use (see +layout.svelte): the dialog primitive stays out of the initial bundle.
	let { open = $bindable(), items, isActive, status }: Props = $props();
</script>

<Sheet.Root bind:open>
	<Sheet.Content side="top" class="p-5 pt-[68px]">
		<Sheet.Title class="sr-only">Menu</Sheet.Title>
		<Sheet.Description class="sr-only">Navigate between the dashboard sections.</Sheet.Description>
		<nav aria-label="Mobile" class="grid gap-1">
			{#each items as item (item.href)}
				<!-- Hrefs arrive already passed through resolve() by the layout. -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					href={item.href}
					onclick={() => (open = false)}
					aria-current={isActive(item.href) ? 'page' : undefined}
					class="flex items-center gap-3 rounded-lg px-[15px] py-[14px] type-headline text-ink-muted transition-[color,background-color] duration-150 ease-out hover:text-ink aria-[current=page]:bg-surface-2 aria-[current=page]:text-ink"
				>
					<item.icon class="size-5" aria-hidden="true" />
					{item.label}
				</a>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{/each}
		</nav>
		<p class="flex items-center gap-2 px-[15px] pb-2 type-caption text-ink-muted" role="status">
			<span class="size-2 rounded-full {status.dot}" aria-hidden="true"></span>
			{status.label}
		</p>
	</Sheet.Content>
</Sheet.Root>
