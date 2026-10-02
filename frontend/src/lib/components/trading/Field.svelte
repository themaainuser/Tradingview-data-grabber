<script lang="ts">
	import type { Snippet } from 'svelte';
	import { Label } from '$lib/components/ui/label';

	interface Props {
		id: string;
		label: string;
		/** One sentence about this field's value, shown under it; replaced by the error when there is one. */
		hint?: string;
		error?: string;
		class?: string;
		children: Snippet;
	}

	let { id, label, hint, error, class: className = '', children }: Props = $props();
</script>

<div class="grid min-w-0 content-start gap-1.5 {className}">
	<Label for={id}>{label}</Label>
	{@render children()}
	{#if error}
		<p class="type-caption text-coral-ink" role="alert" data-testid="field-error">{error}</p>
	{:else if hint}
		<p class="type-caption text-ink-muted">{hint}</p>
	{/if}
</div>
