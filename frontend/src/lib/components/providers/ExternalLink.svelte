<script lang="ts">
	import type { Snippet } from 'svelte';
	import { safeUrl } from '$lib/providers/format';

	interface Props {
		/** A provider-supplied URL. Anything that is not http(s) is rendered as plain text. */
		href: string | null | undefined;
		children: Snippet;
		class?: string;
	}

	let { href, children, class: className = '' }: Props = $props();
	const url = $derived(safeUrl(href));
</script>

{#if url}
	<!-- An external site, not an app route: resolve() does not apply. -->
	<!-- eslint-disable svelte/no-navigation-without-resolve -->
	<a
		href={url}
		target="_blank"
		rel="noopener noreferrer"
		class="text-accent-blue underline-offset-4 hover:underline {className}">{@render children()}</a
	>
	<!-- eslint-enable svelte/no-navigation-without-resolve -->
{:else}
	<span class={className}>{@render children()}</span>
{/if}
