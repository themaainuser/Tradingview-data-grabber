<script lang="ts">
	import Gem from '@lucide/svelte/icons/gem';
	import { cn } from '$lib/utils.js';

	interface Props {
		label?: string;
		class?: string;
	}

	let { label = 'Premium', class: className }: Props = $props();
</script>

<!-- Premium is stated in words and an icon as well as the accent colour, so it never depends on colour alone. -->
<span
	data-testid="premium-badge"
	class={cn(
		'inline-flex w-fit shrink-0 items-center gap-1 rounded-sm bg-orange-ink/15 px-[7px] py-[3px] type-micro font-medium whitespace-nowrap text-orange-ink',
		className
	)}
>
	<Gem class="size-3" aria-hidden="true" />{label}
</span>
