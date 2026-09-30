<script lang="ts">
	import type { Component } from 'svelte';
	import Layout from '../../routes/+layout.svelte';

	let { page: Page }: { page: Component } = $props();
</script>

<!-- Test-only: a page inside the real app shell, so it receives the same app context as in production. -->
<Layout>
	<Page />
</Layout>
