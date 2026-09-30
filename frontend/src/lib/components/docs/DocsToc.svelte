<script lang="ts">
	export interface TocItem {
		id: string;
		label: string;
	}

	interface Props {
		items: readonly TocItem[];
		/** Id of the section currently in view. */
		active: string;
	}

	let { items, active }: Props = $props();
</script>

<!--
  Below the 1199px desktop breakpoint the contents become a single horizontally scrolling row of pills
  (pricing-tab pattern); from 1199px up it is a sticky vertical list beside the content.
-->
<nav
	aria-label="Documentation contents"
	class="sticky top-14 z-20 -mx-5 overflow-x-auto border-b border-hairline-soft bg-canvas/95 px-5 py-2 backdrop-blur-md md:-mx-[30px] md:px-[30px] xl:top-[84px] xl:mx-0 xl:self-start xl:overflow-visible xl:border-0 xl:bg-transparent xl:p-0 xl:backdrop-blur-none"
>
	<p class="mb-3 hidden type-caption text-ink-muted xl:block">On this page</p>
	<ul class="flex w-max gap-1 xl:grid xl:w-auto">
		{#each items as item (item.id)}
			<li>
				<a
					href="#{item.id}"
					aria-current={active === item.id ? 'location' : undefined}
					class="block rounded-pill px-[14px] py-[8px] type-body-sm whitespace-nowrap text-ink-muted transition-[color,background-color] duration-150 ease-out hover:text-ink aria-[current=location]:bg-surface-2 aria-[current=location]:text-ink pointer-coarse:py-[11px]"
				>
					{item.label}
				</a>
			</li>
		{/each}
	</ul>
</nav>
