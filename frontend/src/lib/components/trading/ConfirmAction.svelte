<script lang="ts">
	import type { Snippet } from 'svelte';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';

	interface Props {
		/** The button that starts it. */
		label: string;
		/** The button that does it. */
		confirmLabel: string;
		/** What will happen, in words. */
		description: string;
		/** With real money the word LIVE must be typed first. */
		realMoney: boolean;
		variant?: 'translucent' | 'destructive' | 'ghost' | 'secondary';
		size?: 'xs' | 'sm' | 'default';
		disabled?: boolean;
		/** Return `false` to say the action was refused: the box then stays open so its message can be read. */
		onconfirm: () => void | boolean | Promise<void | boolean>;
		/** Extra controls inside the open confirmation. */
		children?: Snippet;
	}

	let {
		label,
		confirmLabel,
		description,
		realMoney,
		variant = 'translucent',
		size = 'sm',
		disabled = false,
		onconfirm,
		children
	}: Props = $props();

	let open = $state(false);
	let typed = $state('');
	let working = $state(false);
	const ready = $derived(!realMoney || typed.trim() === 'LIVE');

	async function confirm() {
		if (!ready || working) return;
		working = true;
		let refused = false;
		try {
			refused = (await onconfirm()) === false;
		} finally {
			working = false;
			if (!refused) {
				open = false;
				typed = '';
			}
		}
	}
</script>

{#if !open}
	<Button type="button" {variant} {size} {disabled} onclick={() => (open = true)}>{label}</Button>
{:else}
	<div
		class="grid max-w-prose gap-3 rounded-lg bg-canvas p-3 text-left {realMoney
			? 'ring-1 ring-coral-ink'
			: ''}"
		role="group"
		aria-label={label}
		data-testid="confirm-box"
	>
		<p class="flex items-start gap-2 type-body-sm text-pretty">
			{#if realMoney}<TriangleAlert
					class="mt-0.5 size-4 shrink-0 text-coral-ink"
					aria-hidden="true"
				/>{/if}
			<span>{description}</span>
		</p>
		{@render children?.()}
		{#if realMoney}
			<label class="grid gap-1 type-caption text-ink-muted">
				<span
					>This uses real money. Type <strong class="text-coral-ink">LIVE</strong> to continue.</span
				>
				<Input
					bind:value={typed}
					autocomplete="off"
					spellcheck="false"
					aria-label="Type LIVE to confirm"
					class="w-40"
					data-testid="live-confirm"
				/>
			</label>
		{/if}
		<div class="flex flex-wrap gap-2">
			<Button
				type="button"
				variant={realMoney ? 'destructive' : 'default'}
				size="sm"
				disabled={!ready || working}
				onclick={confirm}>{working ? 'Sending…' : confirmLabel}</Button
			>
			<Button
				type="button"
				variant="ghost"
				size="sm"
				disabled={working}
				onclick={() => ((open = false), (typed = ''))}>Cancel</Button
			>
		</div>
	</div>
{/if}
