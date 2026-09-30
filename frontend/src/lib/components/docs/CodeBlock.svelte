<script lang="ts">
	import type { Attachment } from 'svelte/attachments';
	import Check from '@lucide/svelte/icons/check';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import Copy from '@lucide/svelte/icons/copy';
	import { Button } from '$lib/components/ui/button';

	interface Props {
		/** The exact text placed on the clipboard. */
		code: string;
		/** Short caption above the block, e.g. "Terminal 1: backend". */
		label?: string;
	}

	let { code, label }: Props = $props();

	let state = $state<'idle' | 'copied' | 'failed'>('idle');
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function copy() {
		clearTimeout(timer);
		try {
			await navigator.clipboard.writeText(code);
			state = 'copied';
		} catch {
			// Insecure origins (plain http on a LAN address) and denied permissions land here.
			state = 'failed';
		}
		timer = setTimeout(() => (state = 'idle'), 2000);
	}

	// Runs on teardown so a late timeout never writes to a dead component.
	const cleanup: Attachment = () => () => clearTimeout(timer);
</script>

<figure class="grid grid-cols-[minmax(0,1fr)] gap-2" {@attach cleanup}>
	{#if label}
		<figcaption class="type-caption text-ink-muted">{label}</figcaption>
	{/if}
	<div class="flex items-start gap-2 rounded-lg bg-surface-1 py-2 pr-2 pl-[15px]">
		<!-- A horizontally scrollable region must be reachable by keyboard, so it takes focus. -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<pre
			class="min-w-0 flex-1 overflow-x-auto py-[7px] font-mono type-caption text-ink"
			tabindex="0"><code>{code}</code></pre>
		<Button
			variant="ghost"
			size="icon-sm"
			aria-label={state === 'failed' ? 'Copy failed, select the text instead' : 'Copy to clipboard'}
			onclick={copy}
		>
			<!-- One icon per state, cross-faded (scale, opacity, blur) so the swap reads as a single control. -->
			<span class="relative block size-4">
				{#each [{ icon: Copy, on: 'idle', tone: '' }, { icon: Check, on: 'copied', tone: 'text-success-ink' }, { icon: CircleAlert, on: 'failed', tone: 'text-coral-ink' }] as item (item.on)}
					<item.icon
						class="absolute inset-0 transition-[opacity,scale,filter] duration-150 ease-[cubic-bezier(0.2,0,0,1)] {item.tone} {state ===
						item.on
							? 'blur-0 scale-100 opacity-100'
							: 'scale-[0.25] opacity-0 blur-[4px]'}"
						aria-hidden="true"
					/>
				{/each}
			</span>
		</Button>
	</div>
	<span class="sr-only" role="status">
		{state === 'copied'
			? 'Copied'
			: state === 'failed'
				? 'Copy failed. Select the text and copy it manually.'
				: ''}
	</span>
</figure>
