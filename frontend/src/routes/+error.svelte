<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { buttonVariants } from '$lib/components/ui/button';

	// SvelteKit renders this for any unmatched route or load failure, inside the app shell. Without
	// it a mistyped URL produced a blank page.
	const notFound = $derived(page.status === 404);
</script>

<svelte:head>
	<title>{notFound ? 'Page not found' : 'Something went wrong'} · Quant Research</title>
</svelte:head>

<section class="mx-auto grid max-w-[640px] justify-items-start gap-5 py-[60px]" role="alert">
	<p class="type-caption text-ink-muted tabular-nums">Error {page.status}</p>
	<h1 class="type-display-lg">{notFound ? 'Page not found' : 'Something went wrong'}</h1>
	<p class="type-body-lg text-pretty text-ink-muted">
		{notFound
			? 'There is nothing at this address. Check the URL, or head back to one of the sections below.'
			: (page.error?.message ?? 'An unexpected error occurred.')}
	</p>
	<div class="flex flex-wrap gap-2">
		<a href={resolve('/')} class={buttonVariants({ variant: 'default' })}>Datasets</a>
		<a href={resolve('/docs')} class={buttonVariants({ variant: 'secondary' })}>Docs</a>
	</div>
</section>
