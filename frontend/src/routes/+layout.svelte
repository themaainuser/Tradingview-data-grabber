<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import BookOpen from '@lucide/svelte/icons/book-open';
	import ChartArea from '@lucide/svelte/icons/chart-area';
	import CandlestickChart from '@lucide/svelte/icons/chart-candlestick';
	import type { Component } from 'svelte';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import Database from '@lucide/svelte/icons/database';
	import FlaskConical from '@lucide/svelte/icons/flask-conical';
	import Scale from '@lucide/svelte/icons/scale';
	import Gauge from '@lucide/svelte/icons/gauge';
	import PlugZap from '@lucide/svelte/icons/plug-zap';
	import Menu from '@lucide/svelte/icons/menu';
	import X from '@lucide/svelte/icons/x';
	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import ImportCsv from '$lib/components/app/ImportCsv.svelte';
	import ThemeToggle from '$lib/components/app/ThemeToggle.svelte';
	import { AppState, setApp } from '$lib/state/app.svelte';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	// One AppState per mounted app, shared through context (never a module singleton).
	const app = new AppState();
	setApp(app);

	onMount(() => {
		app.datasets.load();
		return app.theme.attach();
	});

	const home = resolve('/');
	const NAV = [
		{ href: home, label: 'Datasets', icon: Database },
		{ href: resolve('/explorer/[[dataset]]', {}), label: 'Explorer', icon: CandlestickChart },
		{ href: resolve('/charts/[[dataset]]', {}), label: 'Charts', icon: ChartArea },
		{ href: resolve('/research'), label: 'Research', icon: FlaskConical },
		{ href: resolve('/verdict/[[dataset]]', {}), label: 'Verdict', icon: Scale },
		{ href: resolve('/sentiment'), label: 'Sentiment', icon: Gauge },
		{
			href: resolve('/providers/[[provider]]/[[endpoint]]', {}),
			label: 'Providers',
			icon: PlugZap
		},
		{ href: resolve('/docs'), label: 'Docs', icon: BookOpen }
	] as const;

	const isActive = (href: string) =>
		href === home ? page.url.pathname === home : page.url.pathname.startsWith(href);

	const count = $derived(app.datasets.items.length);
	const status = $derived(
		app.datasets.status === 'error'
			? { label: 'Backend unreachable', dot: 'bg-coral-ink' }
			: app.datasets.status === 'ready'
				? {
						label: `Backend connected · ${count} dataset${count === 1 ? '' : 's'}`,
						dot: 'bg-success-ink'
					}
				: { label: 'Connecting to backend…', dot: 'bg-ink-muted' }
	);

	let menuOpen = $state(false);
	// The mobile menu (and the dialog primitive behind it) loads the first time it is opened.
	let MobileMenu = $state.raw<Component<any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any

	async function openMenu() {
		menuOpen = true;
		MobileMenu ??= (await import('$lib/components/app/MobileMenu.svelte')).default;
	}

	function imported(id: string) {
		goto(resolve('/explorer/[[dataset]]', { dataset: id }));
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Quant Research</title>
</svelte:head>

<div class="flex min-h-svh flex-col">
	<!-- top-nav: 56px on canvas; wordmark left, links centred, primary pill right -->
	<header
		class="sticky top-0 z-30 h-14 border-b border-hairline-soft bg-canvas/90 backdrop-blur-md"
	>
		<div class="mx-auto flex h-full w-full max-w-[1600px] items-center gap-5 px-5 md:px-[30px]">
			<a href={home} class="flex shrink-0 items-center gap-2.5" aria-label="Quant Research, home">
				<img src={favicon} alt="" class="size-6" width="24" height="24" />
				<span class="hidden font-display text-[17px] font-medium tracking-[-0.03em] sm:inline">
					Quant Research
				</span>
			</a>

			<nav aria-label="Primary" class="hidden flex-1 items-center justify-center gap-1 xl:flex">
				{#each NAV as item (item.href)}
					<a
						href={item.href}
						aria-current={isActive(item.href) ? 'page' : undefined}
						class="inline-flex items-center gap-1.5 rounded-pill px-[14px] py-[8px] type-body-sm text-ink-muted transition-[color,background-color] duration-150 ease-out hover:text-ink aria-[current=page]:bg-surface-2 aria-[current=page]:text-ink"
					>
						<item.icon class="size-4" aria-hidden="true" />
						{item.label}
					</a>
				{/each}
			</nav>

			<div class="ml-auto flex items-center gap-3 xl:ml-0">
				<span
					class="hidden items-center gap-2 type-caption text-ink-muted xl:inline-flex"
					role="status"
					title={status.label}
				>
					<span class="size-2 rounded-full {status.dot}" aria-hidden="true"></span>
					<!-- Seven links, Import CSV and the theme toggle leave no room for the sentence below 2xl: dot only (still announced). -->
					<span class="sr-only 2xl:not-sr-only 2xl:whitespace-nowrap">{status.label}</span>
				</span>
				<ImportCsv datasets={app.datasets} onimported={(bars) => imported(bars.id)} />
				<ThemeToggle class="hidden xl:inline-grid" />

				<Button
					variant="secondary"
					size="icon"
					class="xl:hidden"
					aria-label="Open menu"
					aria-haspopup="dialog"
					aria-expanded={menuOpen}
					onclick={openMenu}
				>
					<Menu aria-hidden="true" />
				</Button>
				{#if MobileMenu}
					<MobileMenu bind:open={menuOpen} items={NAV} {isActive} {status} />
				{/if}
			</div>
		</div>
	</header>

	<main class="mx-auto w-full max-w-[1600px] flex-1 px-5 py-[30px] md:px-[30px] md:py-10">
		{#if app.datasets.importError}
			<Alert.Root variant="destructive" class="mb-[30px]">
				<CircleAlert aria-hidden="true" />
				<Alert.Title>Could not import that file</Alert.Title>
				<Alert.Description>
					<p>{app.datasets.importError}</p>
					<Button
						variant="translucent"
						size="xs"
						class="mt-2"
						onclick={() => app.datasets.dismissImportError()}
					>
						<X aria-hidden="true" /> Dismiss
					</Button>
				</Alert.Description>
			</Alert.Root>
		{/if}
		{@render children()}
	</main>

	<footer class="border-t border-hairline-soft">
		<div
			class="mx-auto grid w-full max-w-[1600px] gap-[30px] px-5 py-16 type-caption text-ink-muted md:grid-cols-[1.4fr_repeat(3,1fr)] md:px-[30px]"
		>
			<div class="grid content-start gap-3">
				<span class="flex items-center gap-2.5 text-ink">
					<img src={favicon} alt="" class="size-6" width="24" height="24" />
					<span class="font-display text-[17px] font-medium tracking-[-0.03em]">Quant Research</span
					>
				</span>
				<p class="max-w-64 type-micro text-pretty">
					Reads only what your own backend serves. Nothing is generated or simulated here.
				</p>
			</div>
			<div class="grid content-start gap-2.5">
				<h2 class="text-ink">Workspace</h2>
				{#each NAV as item (item.href)}
					<a href={item.href} class="w-fit transition-colors duration-150 ease-out hover:text-ink"
						>{item.label}</a
					>
				{/each}
			</div>
			<div class="grid content-start gap-2.5">
				<h2 class="text-ink">Backend</h2>
				<a
					href={resolve('/docs#api')}
					class="w-fit transition-colors duration-150 ease-out hover:text-ink">API reference</a
				>
				<!-- FastAPI's own pages, not SvelteKit routes: a full page load is intended. -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					href="/api/docs"
					data-sveltekit-reload
					class="w-fit transition-colors duration-150 ease-out hover:text-ink"
					>Interactive API (Swagger)</a
				>
				<a
					href="/api/health"
					data-sveltekit-reload
					class="w-fit transition-colors duration-150 ease-out hover:text-ink">Health check</a
				>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			</div>
			<div class="grid content-start gap-2.5">
				<h2 class="text-ink">Notes</h2>
				<p class="text-pretty">Research tool, not investment advice.</p>
				<p class="text-pretty">Costs and slippage are not modeled in forward studies.</p>
			</div>
		</div>
	</footer>
</div>
