<script lang="ts">
	import { onMount } from 'svelte';
	import Gauge from '@lucide/svelte/icons/gauge';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Label } from '$lib/components/ui/label';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Switch } from '$lib/components/ui/switch';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import AreaChart from '$lib/components/charts/AreaChart.svelte';
	import type { AreaSeries } from '$lib/components/charts/types';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import FearGreedGauge from '$lib/components/sentiment/FearGreedGauge.svelte';
	import SnapshotCards from '$lib/components/sentiment/SnapshotCards.svelte';
	import ZoneBar from '$lib/components/sentiment/ZoneBar.svelte';
	import { formatTime } from '$lib/charts/scale';
	import { formatValue } from '$lib/format';
	import { BAND_FILL } from '$lib/sentiment/bands';
	import { RANGES, formatDelta, type RangeKey } from '$lib/sentiment/stats';
	import { getApp } from '$lib/state/app.svelte';

	const { sentiment } = getApp();

	// Always ask again on entry: the backend caches for ten minutes, and the page keeps showing the
	// previous readings while the request is in flight.
	onMount(() => {
		sentiment.load();
	});

	const data = $derived(sentiment.data);
	const view = $derived(sentiment.view);
	const summary = $derived(sentiment.summary);
	const refreshing = $derived(sentiment.status === 'loading');
	const rangeLabel = $derived(RANGES.find((r) => r.key === sentiment.range)?.label ?? '');
	const overlay = $derived(sentiment.showPrice && sentiment.hasPrice);
	const usd = (v: number) => `$${formatValue(v, 'compact')}`;

	const chartSeries = $derived.by<AreaSeries[]>(() => {
		if (!view) return [];
		const series: AreaSeries[] = [
			{
				key: 'score',
				label: 'Fear & Greed',
				color: 'var(--ink)',
				values: view.score,
				kind: 'line',
				axis: 'left'
			}
		];
		if (overlay) {
			series.push({
				key: 'btc',
				label: 'Bitcoin price (USD)',
				color: 'var(--gradient-violet)',
				values: view.price,
				kind: 'line',
				axis: 'right'
			});
		}
		return series;
	});

	const chartBands = $derived(
		(data?.bands ?? []).map((b) => ({
			from: b.from,
			to: b.to,
			color: BAND_FILL[b.key],
			label: b.label
		}))
	);
</script>

<svelte:head>
	<title>Fear &amp; Greed · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-[60px]">
	<header class="grid max-w-[860px] gap-5">
		<p class="type-caption text-ink-muted">Market sentiment</p>
		<h1 class="type-display-lg">Fear &amp; Greed</h1>
		<p class="max-w-[60ch] type-body-lg text-ink-muted">
			How fearful or greedy the crypto market is right now, from 0 (extreme fear) to 100 (extreme
			greed). Your backend fetches the CoinMarketCap index itself; nothing here is estimated.
		</p>
		<div>
			<Button variant="secondary" disabled={refreshing} onclick={() => sentiment.load()}>
				<RefreshCw class={refreshing ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
			</Button>
		</div>
	</header>

	{#if sentiment.status === 'error' && sentiment.error && !data}
		<ErrorPanel
			error={sentiment.error}
			title="Could not load the Fear & Greed index"
			onretry={() => sentiment.load()}
		/>
		<EmptyState
			tone="orange"
			icon={Gauge}
			title="No reading to show"
			description="The index comes from CoinMarketCap through your backend, and nothing is shown when it cannot be fetched. Check the backend's internet access and press Refresh."
		/>
	{:else if !data}
		<div class="grid gap-3" aria-busy="true" aria-label="Loading the Fear and Greed index">
			<Skeleton class="h-96 w-full" />
			<Skeleton class="h-72 w-full" />
		</div>
	{:else}
		{#if data.stale || (sentiment.status === 'error' && sentiment.error)}
			<Alert.Root variant="destructive" data-testid="stale-notice">
				<TriangleAlert aria-hidden="true" />
				<Alert.Title>
					{sentiment.error ? 'Could not refresh the index' : 'Showing the last fetched readings'}
				</Alert.Title>
				<Alert.Description>
					<p class="text-pretty">
						{sentiment.error?.message ?? data.stale_reason} The figures below were fetched from CoinMarketCap
						at
						{formatTime(data.fetched_at, true)} UTC.
					</p>
				</Alert.Description>
			</Alert.Root>
		{/if}

		<section
			class="grid gap-[30px] xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]"
			aria-label="Current reading"
		>
			<FearGreedGauge
				score={data.current.score}
				label={data.current.label}
				band={data.current.band}
				bands={data.bands}
				updated={data.current.time}
			/>
			<SnapshotCards current={data.current} snapshots={data.snapshots} bands={data.bands} />
		</section>

		<section class="grid gap-[30px]" aria-labelledby="history-title">
			<div class="flex flex-wrap items-end gap-[15px]">
				<div class="grid gap-2">
					<h2 id="history-title" class="type-display-md">History</h2>
					<p class="max-w-[60ch] type-body text-ink-muted">
						The index{overlay ? ', with Bitcoin’s price on the right axis,' : ''} over the selected range.
					</p>
				</div>
				<div class="ml-auto flex flex-wrap items-center gap-[15px]">
					{#if sentiment.hasPrice}
						<div class="flex items-center gap-2.5">
							<Switch
								id="show-price"
								checked={sentiment.showPrice}
								onCheckedChange={(v) => (sentiment.showPrice = v)}
							/>
							<Label for="show-price">Bitcoin price</Label>
						</div>
					{/if}
					<ToggleGroup.Root
						type="single"
						size="sm"
						value={sentiment.range}
						onValueChange={(v) => v && (sentiment.range = v as RangeKey)}
						aria-label="History range"
					>
						{#each RANGES as r (r.key)}
							<ToggleGroup.Item value={r.key}>{r.label}</ToggleGroup.Item>
						{/each}
					</ToggleGroup.Root>
				</div>
			</div>

			<Card.Root class="shadow-float">
				{#if view}
					<AreaChart
						time={view.time}
						series={chartSeries}
						bands={chartBands}
						leftDomain={[0, 100]}
						leftFormat={(v) => String(Math.round(v))}
						rightFormat={usd}
						height={340}
						label="Fear and Greed index, range {rangeLabel}{overlay
							? ', with Bitcoin price'
							: ''}. Coloured bands mark extreme fear, fear, neutral, greed and extreme greed."
					/>
				{/if}
			</Card.Root>

			<div class="grid gap-[30px] lg:grid-cols-2">
				<Card.Root>
					<Card.Header>
						<Card.Title>Time in each zone</Card.Title>
						<Card.Description>Share of readings in the selected range.</Card.Description>
					</Card.Header>
					<Card.Content><ZoneBar zones={sentiment.zones} /></Card.Content>
				</Card.Root>

				<Card.Root>
					<Card.Header>
						<Card.Title>Range summary</Card.Title>
						<Card.Description
							>{rangeLabel === 'All' ? 'Whole history' : `Last ${rangeLabel}`}</Card.Description
						>
					</Card.Header>
					<Card.Content>
						{#if summary}
							<dl class="grid grid-cols-2 gap-x-5 gap-y-4 tabular-nums" data-testid="range-summary">
								<div>
									<dt class="type-caption text-ink-muted">Average</dt>
									<dd class="type-display-md">{summary.mean.toFixed(1)}</dd>
								</div>
								<div>
									<dt class="type-caption text-ink-muted">Net change</dt>
									<dd class="type-display-md">{formatDelta(summary.change)}</dd>
								</div>
								<div>
									<dt class="type-caption text-ink-muted">Highest</dt>
									<dd class="type-body-sm">
										{summary.high.score}
										<span class="type-caption text-ink-muted"
											>on {formatTime(summary.high.time, false)}</span
										>
									</dd>
								</div>
								<div>
									<dt class="type-caption text-ink-muted">Lowest</dt>
									<dd class="type-body-sm">
										{summary.low.score}
										<span class="type-caption text-ink-muted"
											>on {formatTime(summary.low.time, false)}</span
										>
									</dd>
								</div>
							</dl>
						{:else}
							<p class="type-body text-ink-muted" role="status">No readings in this range.</p>
						{/if}
					</Card.Content>
				</Card.Root>
			</div>
		</section>

		<footer class="grid max-w-[860px] gap-2 type-caption text-ink-muted">
			<p class="text-pretty">
				Source:
				<!-- External site, not an app route: resolve() does not apply. -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					class="text-accent-blue hover:underline"
					href={data.source.url}
					target="_blank"
					rel="noreferrer noopener">{data.source.index}</a
				>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
				by {data.source.name}. Your backend reads the public endpoint CoinMarketCap's own chart page
				uses. It needs no API key but is not a published API, so it may change or limit access.
				Readings are cached for up to 10 minutes; last fetched {formatTime(data.fetched_at, true)} UTC.
			</p>
			<p class="text-pretty">
				Bitcoin price comes in the same CoinMarketCap payload. A sentiment index describes the
				market; it is not investment advice. Check CoinMarketCap's terms before redistributing the
				data.
			</p>
		</footer>
	{/if}
</div>
