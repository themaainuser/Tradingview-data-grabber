<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ChartArea from '@lucide/svelte/icons/chart-area';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Label } from '$lib/components/ui/label';
	import * as Select from '$lib/components/ui/select';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as ToggleGroup from '$lib/components/ui/toggle-group';
	import AreaChart from '$lib/components/charts/AreaChart.svelte';
	import BarChart from '$lib/components/charts/BarChart.svelte';
	import HBarChart from '$lib/components/charts/HBarChart.svelte';
	import Heatmap from '$lib/components/charts/Heatmap.svelte';
	import SectionCard from '$lib/components/charts/SectionCard.svelte';
	import EmptyState from '$lib/components/app/EmptyState.svelte';
	import ErrorPanel from '$lib/components/app/ErrorPanel.svelte';
	import { binIndexOf, formatSignedPct, histogramLabels } from '$lib/charts/distribution';
	import { formatTime } from '$lib/charts/scale';
	import { formatDuration, formatValue } from '$lib/format';
	import { getApp } from '$lib/state/app.svelte';
	import {
		MAX_CORRELATION,
		PROFILE_BINS,
		VOLATILITY_WINDOWS,
		type ActivityMetric
	} from '$lib/state/charts.svelte';

	const { datasets, charts } = getApp();

	const requested = $derived(page.params.dataset ?? null);

	// URL -> store: /charts/<id> (a link, reload or shared URL) opens that dataset.
	$effect(() => {
		const id = requested;
		if (!id) return;
		untrack(() => {
			if (charts.datasetId !== id || charts.status === 'idle') charts.open(id);
		});
	});

	function choose(id: string) {
		goto(resolve('/charts/[[dataset]]', { dataset: id }), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	const data = $derived(charts.charts);
	const selected = $derived(datasets.usable.find((d) => d.id === requested));
	const selectedLabel = $derived(
		selected
			? `${selected.symbol}${selected.timeframe ? ` · ${selected.timeframe}` : ''}`
			: 'Choose a dataset'
	);
	// Two decimals for readable prices; tiny prices (below 1) keep the precision they need.
	const price = (v: number) =>
		Math.abs(v) < 1
			? formatValue(v, 'price')
			: v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const pct = (v: number) => `${v.toFixed(2)}%`;
	const signed = (v: number) => formatSignedPct(v, 2);

	// --- return distribution ------------------------------------------------------------------
	const dist = $derived(data?.return_distribution ?? null);
	const distLabels = $derived(dist ? histogramLabels(dist.edges) : []);
	const distMarkers = $derived.by(() => {
		if (!dist) return [];
		const index = binIndexOf(dist.edges, dist.stats.var_95_pct);
		return index < 0 ? [] : [{ index, label: 'VaR 95%' }];
	});

	// --- activity heatmap ---------------------------------------------------------------------
	const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
	const ACTIVITY: Record<
		ActivityMetric,
		{
			label: string;
			scale: 'sequential' | 'diverging';
			format: (v: number) => string;
			note: string;
		}
	> = {
		range_pct: {
			label: 'Bar range',
			scale: 'sequential',
			format: pct,
			note: 'Average high-to-low range of a bar, as a share of its open.'
		},
		volume: {
			label: 'Volume',
			scale: 'sequential',
			format: (v) => formatValue(v, 'compact'),
			note: 'Average volume per bar.'
		},
		return_pct: {
			label: 'Return',
			scale: 'diverging',
			format: signed,
			note: 'Average close-to-close return of a bar.'
		}
	};
	const activity = $derived(data?.activity ?? null);
	const activityCols = $derived(
		activity ? activity.hours.map((h) => String(h).padStart(2, '0')) : []
	);
	const activityRows = $derived(
		activity ? activity.weekdays.map((d) => WEEKDAYS[d] ?? String(d)) : []
	);

	// --- seasonality --------------------------------------------------------------------------
	let seasonMetric = $state<'mean_return_pct' | 'hit_rate_pct'>('mean_return_pct');
	const seasonValues = (b: {
		mean_return_pct: (number | null)[];
		hit_rate_pct: (number | null)[];
	}) => (seasonMetric === 'mean_return_pct' ? b.mean_return_pct : b.hit_rate_pct);
	const seasonFormat = $derived(
		seasonMetric === 'mean_return_pct' ? signed : (v: number) => `${v.toFixed(1)}%`
	);
	const seasonUnavailable = $derived(
		data && !data.seasonality.by_weekday && !data.seasonality.by_hour
			? (data.unavailable['seasonality.by_weekday'] ??
					data.unavailable['seasonality.by_hour'] ??
					'there are not enough bars.')
			: null
	);

	// --- correlation --------------------------------------------------------------------------
	const correlation = $derived(charts.correlation);
	const correlationPeriod = $derived(
		correlation
			? `${formatTime(correlation.start, false)} to ${formatTime(correlation.end, false)} UTC`
			: ''
	);
</script>

<svelte:head>
	<title>Charts · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-[60px]">
	<header class="grid max-w-[860px] gap-5">
		<p class="type-caption text-ink-muted">Backend analysis</p>
		<h1 class="type-display-lg">Charts</h1>
		<p class="max-w-[60ch] type-body-lg text-ink-muted">
			Volume profile, return distribution, drawdown, rolling volatility and time-of-week patterns,
			all computed by your backend from the captures. It is the same code that draws the PNGs from
			<code class="rounded-xs bg-surface-2 px-[5px] py-[2px] font-mono type-caption"
				>tvdata chart</code
			>.
		</p>
		<div>
			<Select.Root
				type="single"
				value={requested ?? ''}
				onValueChange={choose}
				disabled={datasets.usable.length === 0}
			>
				<Select.Trigger class="w-72" aria-label="Dataset">{selectedLabel}</Select.Trigger>
				<Select.Content>
					{#each datasets.usable as d (d.id)}
						<Select.Item value={d.id} label={d.symbol}>
							{d.symbol}{d.timeframe ? ` · ${d.timeframe}` : ''}
							<span class="ml-auto type-caption text-ink-muted tabular-nums"
								>{d.rows.toLocaleString('en-US')}</span
							>
						</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
		</div>
	</header>

	{#if datasets.status === 'ready' && datasets.usable.length === 0}
		<EmptyState
			tone="violet"
			icon={ChartArea}
			title="No backend datasets to chart"
			description="These charts are computed by the backend, so they need captures on the backend; files imported in the browser are not available here. Capture bars, then press Refresh on the Datasets page."
		/>
	{:else if !requested}
		<EmptyState
			icon={ChartArea}
			title="Choose a dataset"
			description="Pick a capture above to see its volume profile, return distribution, drawdown and more."
		/>
	{:else if charts.status === 'error' && charts.error && !data}
		<ErrorPanel
			error={charts.error}
			title="Could not load the charts"
			onretry={() => charts.reload()}
		/>
	{:else if !data}
		<div class="grid gap-[30px]" aria-busy="true" aria-label="Loading charts">
			<Skeleton class="h-96 w-full" />
			<Skeleton class="h-72 w-full" />
		</div>
	{:else}
		{#if charts.status === 'error' && charts.error}
			<ErrorPanel
				error={charts.error}
				title="Could not refresh the charts"
				onretry={() => charts.reload()}
			/>
		{/if}

		<dl
			class="grid grid-cols-2 gap-3 tabular-nums xl:grid-cols-6 sm:grid-cols-3"
			aria-label="Dataset summary"
			data-testid="charts-summary"
			aria-busy={charts.status === 'loading'}
		>
			{#each [{ label: 'Bars', value: data.bars.toLocaleString('en-US') }, { label: 'Bar interval', value: formatDuration(data.interval_seconds) }, { label: 'Std dev per bar', value: dist ? pct(dist.stats.std_pct) : '\u2014' }, { label: 'Up bars', value: dist ? `${dist.stats.positive_pct.toFixed(1)}%` : '\u2014' }, { label: 'Max drawdown', value: data.drawdown ? signed(data.drawdown.max_drawdown_pct) : '\u2014' }, { label: 'Current drawdown', value: data.drawdown ? signed(data.drawdown.current_drawdown_pct) : '\u2014' }] as item (item.label)}
				<div class="grid gap-1 rounded-xl bg-surface-1 p-[15px]">
					<dt class="type-caption text-ink-muted">{item.label}</dt>
					<dd class="type-display-md">{item.value}</dd>
				</div>
			{/each}
		</dl>

		<div class="grid grid-cols-[minmax(0,1fr)] gap-[30px] xl:grid-cols-2">
			<SectionCard
				id="volume-profile"
				title="Volume profile"
				description="Where trading happened by price. The point of control (POC) is the busiest price; the value area holds 70% of the volume."
			>
				{#snippet actions()}
					<ToggleGroup.Root
						type="single"
						size="sm"
						value={String(charts.bins)}
						onValueChange={(v) => v && charts.setBins(Number(v))}
						aria-label="Price bins"
					>
						{#each PROFILE_BINS as n (n)}<ToggleGroup.Item value={String(n)}>{n}</ToggleGroup.Item
							>{/each}
					</ToggleGroup.Root>
				{/snippet}
				<HBarChart
					edges={data.volume_profile.edges}
					values={data.volume_profile.volume}
					markers={[{ value: data.volume_profile.poc, label: 'POC' }]}
					range={{
						low: data.volume_profile.value_low,
						high: data.volume_profile.value_high,
						label: 'Value area'
					}}
					priceFormat={(v) => price(v)}
					valueFormat={(v) => formatValue(v, 'compact')}
					height={380}
					label="Volume profile for {data.symbol}: the busiest price is {price(
						data.volume_profile.poc
					)} and the value area spans {price(data.volume_profile.value_low)} to {price(
						data.volume_profile.value_high
					)}."
				/>
				<p class="type-caption text-ink-muted tabular-nums">
					POC {price(data.volume_profile.poc)} · value area {price(data.volume_profile.value_low)}
					to {price(data.volume_profile.value_high)}
				</p>
			</SectionCard>

			<SectionCard
				id="return-distribution"
				title="Return distribution"
				description="How bar-to-bar returns are spread, against a normal curve with the same mean and spread. Fat tails show as bars above the curve at the edges."
				unavailable={data.unavailable.return_distribution}
			>
				{#if dist}
					<BarChart
						labels={distLabels}
						values={dist.counts}
						overlay={dist.normal}
						overlayLabel="Normal fit"
						markers={distMarkers}
						colorBy="solid"
						format={(v) => `${Math.round(v).toLocaleString('en-US')} bars`}
						height={300}
						label="Histogram of {dist.stats.count.toLocaleString(
							'en-US'
						)} bar returns with a fitted normal curve. Average {signed(
							dist.stats.mean_pct
						)}, standard deviation {pct(dist.stats.std_pct)}."
					/>
					<dl
						class="grid grid-cols-2 gap-x-5 gap-y-3 tabular-nums sm:grid-cols-4"
						data-testid="distribution-stats"
					>
						{#each [{ label: 'Mean', value: signed(dist.stats.mean_pct) }, { label: 'Std dev', value: pct(dist.stats.std_pct) }, { label: 'Skew', value: dist.stats.skew === null ? '\u2014' : dist.stats.skew.toFixed(2) }, { label: 'Excess kurtosis', value: dist.stats.excess_kurtosis === null ? '\u2014' : dist.stats.excess_kurtosis.toFixed(2) }, { label: 'VaR 95%', value: signed(dist.stats.var_95_pct) }, { label: 'CVaR 95%', value: signed(dist.stats.cvar_95_pct) }, { label: 'Worst bar', value: signed(dist.stats.min_pct) }, { label: 'Best bar', value: signed(dist.stats.max_pct) }] as s (s.label)}
							<div>
								<dt class="type-caption text-ink-muted">{s.label}</dt>
								<dd class="type-body-sm">{s.value}</dd>
							</div>
						{/each}
					</dl>
					{#if dist.outliers.below + dist.outliers.above > 0}
						<p class="type-micro text-ink-muted">
							{dist.outliers.below + dist.outliers.above} extreme bars ({dist.outliers.below} below, {dist
								.outliers.above}
							above) lie outside the plotted range but are included in the statistics.
						</p>
					{/if}
				{/if}
			</SectionCard>
		</div>

		<SectionCard
			id="drawdown"
			title="Drawdown"
			description="How far the close sits below its running peak. Deeper and longer dips mean more pain for a buy-and-hold holder."
			unavailable={data.unavailable.drawdown}
		>
			{#if data.drawdown}
				{@const dd = data.drawdown}
				<AreaChart
					time={dd.time}
					series={[
						{
							key: 'dd',
							label: 'Drawdown',
							color: 'var(--coral-ink)',
							values: dd.drawdown_pct,
							kind: 'area',
							axis: 'left'
						}
					]}
					leftDomain={[Math.min(dd.max_drawdown_pct * 1.1, -1), 0]}
					baseline={0}
					leftFormat={(v) => `${v.toFixed(1)}%`}
					height={260}
					label="Drawdown from the running peak. The deepest drop was {signed(
						dd.max_drawdown_pct
					)}; the current drawdown is {signed(dd.current_drawdown_pct)}."
				/>
				<dl
					class="grid grid-cols-2 gap-x-5 gap-y-3 tabular-nums sm:grid-cols-4"
					data-testid="drawdown-stats"
				>
					<div>
						<dt class="type-caption text-ink-muted">Deepest drop</dt>
						<dd class="type-body-sm">{signed(dd.max_drawdown_pct)}</dd>
					</div>
					<div>
						<dt class="type-caption text-ink-muted">Peak to trough</dt>
						<dd class="type-body-sm">
							{formatTime(dd.peak_time, data.intraday)} &rarr; {formatTime(
								dd.trough_time,
								data.intraday
							)}
						</dd>
					</div>
					<div>
						<dt class="type-caption text-ink-muted">Recovered</dt>
						<dd class="type-body-sm">
							{dd.recovered_time === null
								? 'Not yet'
								: formatTime(dd.recovered_time, data.intraday)}
						</dd>
					</div>
					<div>
						<dt class="type-caption text-ink-muted">Longest underwater</dt>
						<dd class="type-body-sm">{dd.longest_underwater_bars.toLocaleString('en-US')} bars</dd>
					</div>
				</dl>
			{/if}
		</SectionCard>

		<SectionCard
			id="rolling-volatility"
			title="Rolling volatility"
			description="Standard deviation of bar returns over a sliding window, per bar (not annualised). Spikes mark turbulent stretches."
			unavailable={data.unavailable.rolling_volatility}
		>
			{#snippet actions()}
				<ToggleGroup.Root
					type="single"
					size="sm"
					value={String(charts.window)}
					onValueChange={(v) => v && charts.setWindow(Number(v))}
					aria-label="Window in bars"
				>
					{#each VOLATILITY_WINDOWS as n (n)}<ToggleGroup.Item value={String(n)}
							>{n}</ToggleGroup.Item
						>{/each}
				</ToggleGroup.Root>
			{/snippet}
			{#if data.rolling_volatility}
				{@const rv = data.rolling_volatility}
				<AreaChart
					time={rv.time}
					series={[
						{
							key: 'vol',
							label: `${rv.window}-bar volatility`,
							color: 'var(--orange-ink)',
							values: rv.value_pct,
							kind: 'line',
							axis: 'left'
						}
					]}
					leftFormat={(v) => `${v.toFixed(2)}%`}
					height={240}
					label="Rolling {rv.window}-bar standard deviation of returns, in percent per bar."
				/>
			{/if}
		</SectionCard>

		<SectionCard
			id="activity"
			title="Activity by time of week"
			description="When the market is busy. Rows are weekdays and columns are UTC hours; empty cells have no bars."
			unavailable={data.unavailable.activity}
		>
			{#snippet actions()}
				<ToggleGroup.Root
					type="single"
					size="sm"
					value={charts.activityMetric}
					onValueChange={(v) => v && (charts.activityMetric = v as ActivityMetric)}
					aria-label="Heatmap metric"
				>
					{#each Object.entries(ACTIVITY) as [key, meta] (key)}<ToggleGroup.Item value={key}
							>{meta.label}</ToggleGroup.Item
						>{/each}
				</ToggleGroup.Root>
			{/snippet}
			{#if activity}
				{@const meta = ACTIVITY[charts.activityMetric]}
				<Heatmap
					rows={activityRows}
					cols={activityCols}
					values={activity.metrics[charts.activityMetric]}
					scale={meta.scale}
					format={meta.format}
					cellHeight={30}
					legend={meta.scale === 'diverging'
						? { low: 'Negative', high: 'Positive' }
						: { low: 'Quiet', high: 'Busy' }}
					label="{meta.label} by weekday and UTC hour. {meta.note}"
				/>
				<p class="type-caption text-ink-muted">{meta.note}</p>
			{/if}
		</SectionCard>

		<SectionCard
			id="seasonality"
			title="Seasonality"
			description="Average return and share of up bars by weekday and by hour. Patterns in a short capture are often noise, so check the counts before trusting one."
			unavailable={seasonUnavailable}
		>
			{#snippet actions()}
				<ToggleGroup.Root
					type="single"
					size="sm"
					value={seasonMetric}
					onValueChange={(v) => v && (seasonMetric = v as typeof seasonMetric)}
					aria-label="Seasonality metric"
				>
					<ToggleGroup.Item value="mean_return_pct">Mean return</ToggleGroup.Item>
					<ToggleGroup.Item value="hit_rate_pct">Up bars</ToggleGroup.Item>
				</ToggleGroup.Root>
			{/snippet}
			<div class="grid gap-[30px]">
				{#each [{ key: 'weekday', title: 'By weekday (UTC)', bucket: data.seasonality.by_weekday, reason: data.unavailable['seasonality.by_weekday'] }, { key: 'hour', title: 'By hour (UTC)', bucket: data.seasonality.by_hour, reason: data.unavailable['seasonality.by_hour'] }] as block (block.key)}
					<div class="grid gap-2" data-testid="seasonality-{block.key}">
						<h3 class="type-body-sm">{block.title}</h3>
						{#if block.bucket}
							<BarChart
								labels={block.bucket.labels}
								values={seasonValues(block.bucket)}
								colorBy={seasonMetric === 'mean_return_pct' ? 'sign' : 'solid'}
								format={seasonFormat}
								height={200}
								label="{seasonMetric === 'mean_return_pct'
									? 'Average return'
									: 'Share of up bars'} {block.title.toLowerCase()}"
							/>
						{:else}
							<p class="type-caption text-ink-muted" role="status">
								Not available: {block.reason ?? 'not enough bars.'}
							</p>
						{/if}
					</div>
				{/each}
			</div>
		</SectionCard>
	{/if}

	{#if datasets.usable.length > 1}
		<SectionCard
			id="correlation"
			title="Correlation"
			description="How closely the selected datasets' bar returns move together, over the bars they share. 1 means in lockstep, 0 unrelated, −1 opposite."
		>
			<fieldset class="grid gap-3">
				<legend class="mb-1 type-caption text-ink-muted"
					>Choose two or more datasets (up to {MAX_CORRELATION})</legend
				>
				<ul class="flex flex-wrap gap-x-5 gap-y-3">
					{#each datasets.usable as d (d.id)}
						<li class="flex items-center gap-2.5">
							<Checkbox
								id="corr-{d.id}"
								checked={charts.correlationIds.includes(d.id)}
								onCheckedChange={() => charts.toggleCorrelation(d.id)}
							/>
							<Label for="corr-{d.id}" class="cursor-pointer"
								>{d.symbol}{d.timeframe ? ` · ${d.timeframe}` : ''}</Label
							>
						</li>
					{/each}
				</ul>
			</fieldset>
			<div aria-live="polite" aria-busy={charts.correlationStatus === 'loading'}>
				{#if charts.correlationIds.length < 2}
					<p class="type-body text-ink-muted">Select at least two datasets to compare.</p>
				{:else if charts.correlationStatus === 'error' && charts.correlationError}
					<p class="type-body text-coral-ink" role="alert">
						{charts.correlationError.message}
					</p>
				{:else if correlation}
					<div class="grid gap-3" data-testid="correlation-result">
						<Heatmap
							rows={correlation.labels}
							cols={correlation.labels}
							values={correlation.matrix}
							scale="diverging"
							domain={[-1, 1]}
							format={(v) => v.toFixed(2)}
							showValues
							square
							cellHeight={56}
							legend={{ low: '−1 opposite', high: '+1 together' }}
							label="Return correlation matrix for {correlation.labels.join(', ')}."
						/>
						<p class="type-caption text-ink-muted tabular-nums">
							{correlation.observations.toLocaleString('en-US')} overlapping returns, {correlationPeriod}.
						</p>
					</div>
				{:else}
					<Skeleton class="h-40 w-full" />
				{/if}
			</div>
		</SectionCard>
	{/if}
</div>
