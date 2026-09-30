<script lang="ts">
	import Layout from '../../routes/+layout.svelte';
	import Docs from '../../routes/docs/+page.svelte';
</script>

<!-- Test-only: the Docs page inside the real app shell, so padding and negative margins match production. -->
<Layout>
	<Docs />
</Layout>
