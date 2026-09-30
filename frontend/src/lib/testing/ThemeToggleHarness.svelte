<script lang="ts">
	import ThemeToggle from '$lib/components/app/ThemeToggle.svelte';
	import { setApp, type AppState } from '$lib/state/app.svelte';

	// Test-only: the toggle with the app context the root layout would provide.
	let { app, variant = 'icon' }: { app: AppState; variant?: 'icon' | 'labelled' } = $props();
	// Context is provided once at mount, like the root layout does.
	// svelte-ignore state_referenced_locally
	setApp(app);
</script>

<ThemeToggle {variant} />
