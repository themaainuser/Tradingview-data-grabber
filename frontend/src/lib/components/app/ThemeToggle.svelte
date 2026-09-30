<script lang="ts">
	import Monitor from '@lucide/svelte/icons/monitor';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';
	import { getApp } from '$lib/state/app.svelte';
	import { THEME_PREFERENCES, type ThemePreference } from '$lib/state/theme.svelte';
	import { cn } from '$lib/utils';

	interface Props {
		/** `icon`: compact pill for the header. `labelled`: icon and word per segment, for the mobile menu. */
		variant?: 'icon' | 'labelled';
		class?: string;
	}

	let { variant = 'icon', class: className }: Props = $props();

	const theme = getApp().theme;

	const OPTIONS = {
		system: { label: 'System', title: 'System theme: follow the device setting', icon: Monitor },
		dark: { label: 'Dark', title: 'Dark theme', icon: Moon },
		light: { label: 'Light', title: 'Light theme', icon: Sun }
	} as const satisfies Record<ThemePreference, object>;

	const index = $derived(THEME_PREFERENCES.indexOf(theme.preference));

	// Radio-group keyboard model: arrows move the selection (and focus) and wrap; only the
	// selected radio is in the tab order.
	function onkeydown(event: KeyboardEvent & { currentTarget: HTMLElement }) {
		const last = THEME_PREFERENCES.length - 1;
		const next =
			event.key === 'ArrowRight' || event.key === 'ArrowDown'
				? (index + 1) % THEME_PREFERENCES.length
				: event.key === 'ArrowLeft' || event.key === 'ArrowUp'
					? (index + last) % THEME_PREFERENCES.length
					: event.key === 'Home'
						? 0
						: event.key === 'End'
							? last
							: -1;
		if (next < 0) return;
		event.preventDefault();
		theme.set(THEME_PREFERENCES[next]);
		event.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')[next]?.focus();
	}
</script>

<!-- The group is a container: focus lives on the roving-tabindex radios inside it. -->
<!-- svelte-ignore a11y_interactive_supports_focus -->
<div
	role="radiogroup"
	aria-label="Theme"
	data-slot="theme-toggle"
	class={cn(
		'relative inline-grid shrink-0 grid-cols-3 rounded-pill bg-surface-1 p-[3px]',
		className
	)}
	{onkeydown}
>
	<!-- The selection: one pill that slides under the chosen segment (transform only, so nothing reflows). -->
	<span
		class="pointer-events-none absolute inset-y-[3px] left-[3px] w-[calc((100%-6px)/3)] rounded-pill bg-primary transition-transform duration-150 ease-out"
		style:transform="translateX({index * 100}%)"
		aria-hidden="true"
	></span>
	{#each THEME_PREFERENCES as value (value)}
		{@const option = OPTIONS[value]}
		{@const checked = theme.preference === value}
		<button
			type="button"
			role="radio"
			aria-checked={checked}
			aria-label={variant === 'icon' ? option.label : undefined}
			title={option.title}
			tabindex={checked ? 0 : -1}
			data-value={value}
			class={cn(
				'relative z-10 inline-flex items-center justify-center gap-1.5 rounded-pill type-caption transition-colors duration-150 ease-out',
				variant === 'icon' ? 'size-7 pointer-coarse:size-11' : 'h-11 px-3',
				checked ? 'text-on-primary' : 'text-ink-muted hover:text-ink'
			)}
			onclick={() => theme.set(value)}
		>
			<option.icon class="size-4 shrink-0" aria-hidden="true" />
			{#if variant === 'labelled'}{option.label}{/if}
		</button>
	{/each}
</div>
