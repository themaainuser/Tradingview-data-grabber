<script lang="ts">
	import type { Snippet } from 'svelte';
	import { cn } from '$lib/utils';

	interface Props {
		/** Gradient family member. Orange carries black ink; violet and magenta carry white. */
		tone?: 'violet' | 'magenta' | 'orange';
		class?: string;
		children: Snippet;
	}

	// Spotlight cards are scarce by design: one per page at most, never a section background.
	const TONES = {
		violet: 'spotlight-violet',
		magenta: 'spotlight-magenta',
		orange: 'spotlight-orange'
	} as const;

	let { tone = 'violet', class: className, children }: Props = $props();
</script>

<div class={cn('rounded-xxl p-[30px]', TONES[tone], className)} data-slot="spotlight-card">
	{@render children()}
</div>
