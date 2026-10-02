<script lang="ts">
	import KeyRound from '@lucide/svelte/icons/key-round';
	import type { TradingEnvironment } from '$lib/api/trading';

	let { environment }: { environment: TradingEnvironment } = $props();
</script>

<section
	class="grid max-w-[72ch] gap-3 rounded-xl bg-surface-1 p-5"
	data-testid="trading-setup"
	aria-labelledby="setup-title"
>
	<h2 id="setup-title" class="flex items-center gap-2 type-headline">
		<KeyRound class="size-5" aria-hidden="true" />
		{environment.label} is not set up
	</h2>
	{#if !environment.enabled}
		<p class="type-body-sm text-pretty">
			Live trading places real orders with real money, so it is off. To turn it on, set
			<code class="font-mono text-ink">{environment.enable_env}=true</code> together with
			<code class="font-mono text-ink">{environment.key_env}</code> and
			<code class="font-mono text-ink">{environment.secret_env}</code> in the backend's environment
			or its
			<code class="font-mono text-ink">.env</code> file, and restart it.
		</p>
	{:else}
		<p class="type-body-sm text-pretty">
			Set <code class="font-mono text-ink">{environment.key_env}</code> and
			<code class="font-mono text-ink">{environment.secret_env}</code>
			{#if environment.fallback_key_env}
				(or <code class="font-mono text-ink">{environment.fallback_key_env}</code> and
				<code class="font-mono text-ink">{environment.fallback_secret_env}</code>)
			{/if}
			in the backend's environment or its <code class="font-mono text-ink">.env</code> file and restart
			it.
		</p>
	{/if}
	<p class="type-caption text-pretty text-ink-muted">
		{environment.real_money
			? 'Use the keys of your live Alpaca account. They only work on the live host.'
			: 'Use the keys of your paper account from the Alpaca dashboard. They only work on the paper host, and the key stays on the server: this page never sees it.'}
		Nothing is requested until the keys are set.
	</p>
</section>
