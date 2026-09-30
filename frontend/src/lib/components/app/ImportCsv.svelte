<script lang="ts">
	import Upload from '@lucide/svelte/icons/upload';
	import { Button, type ButtonVariant } from '$lib/components/ui/button';
	import type { Bars } from '$lib/api/validate';
	import type { DatasetsStore } from '$lib/state/datasets.svelte';

	interface Props {
		datasets: DatasetsStore;
		onimported: (bars: Bars) => void;
		variant?: ButtonVariant;
	}

	let { datasets, onimported, variant = 'default' }: Props = $props();
	let input: HTMLInputElement | undefined = $state();
	let busy = $state(false);

	// Rejections surface in the app shell (datasets.importError), so the button stays a single pill.
	async function pick(event: Event & { currentTarget: HTMLInputElement }) {
		const target = event.currentTarget;
		const file = target.files?.[0];
		if (!file) return;
		busy = true;
		const bars = await datasets.importFile(file);
		busy = false;
		// Allow re-importing the same file after fixing it.
		target.value = '';
		if (bars) onimported(bars);
	}
</script>

<input
	bind:this={input}
	type="file"
	accept=".csv,text/csv"
	class="sr-only"
	tabindex="-1"
	aria-hidden="true"
	onchange={pick}
/>
<Button {variant} size="sm" disabled={busy} onclick={() => input?.click()}>
	<Upload aria-hidden="true" />
	{busy ? 'Reading…' : 'Import CSV'}
</Button>
