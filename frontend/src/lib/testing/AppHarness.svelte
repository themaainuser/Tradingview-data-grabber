<script lang="ts">
	import type { Component } from 'svelte';
	import { setApp, type AppState } from '$lib/state/app.svelte';

	// Test-only: mounts a component with the same context the root layout provides.
	let { app, component: Page }: { app: AppState; component: Component } = $props();
	// Context is provided once at mount, like the root layout does.
	// svelte-ignore state_referenced_locally
	setApp(app);
</script>

<Page />
