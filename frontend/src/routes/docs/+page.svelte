<script lang="ts">
	import type { Attachment } from 'svelte/attachments';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import { resolve } from '$app/paths';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { buttonVariants } from '$lib/components/ui/button';
	import ApiReference from '$lib/components/docs/ApiReference.svelte';
	import CodeBlock from '$lib/components/docs/CodeBlock.svelte';
	import DocSection from '$lib/components/docs/DocSection.svelte';
	import DocsToc, { type TocItem } from '$lib/components/docs/DocsToc.svelte';
	import IndicatorReference from '$lib/components/docs/IndicatorReference.svelte';
	import MetricGlossary from '$lib/components/docs/MetricGlossary.svelte';
	import OperatorReference from '$lib/components/docs/OperatorReference.svelte';
	import { API_ENDPOINTS } from '$lib/docs/api-reference';
	import { observeSections } from '$lib/docs/scrollspy';
	import { generatePresets } from '$lib/explorer/presets';
	import { MAX_IMPORT_BYTES } from '$lib/data/csv';
	import { INDICATORS } from '$lib/indicators';
	import { cn } from '$lib/utils';

	const SECTIONS: readonly TocItem[] = [
		{ id: 'quick-start', label: 'Quick start' },
		{ id: 'data', label: 'Data' },
		{ id: 'explorer', label: 'Explorer' },
		{ id: 'filters', label: 'Filters' },
		{ id: 'indicators', label: 'Indicators' },
		{ id: 'research', label: 'Research' },
		{ id: 'verdict', label: 'Verdict' },
		{ id: 'charts', label: 'Charts' },
		{ id: 'sentiment', label: 'Sentiment' },
		{ id: 'providers', label: 'Providers' },
		{ id: 'api', label: 'API reference' },
		{ id: 'troubleshooting', label: 'Troubleshooting' }
	];

	let active = $state(SECTIONS[0].id);

	// Wires the scroll-spy to the rendered sections; the cleanup disconnects the observer on teardown.
	const spy: Attachment<HTMLElement> = (root) =>
		observeSections(
			root,
			SECTIONS.map((s) => s.id),
			(id) => (active = id)
		);

	// Commands shown in the quick start; each is copied to the clipboard exactly as written.
	const INSTALL = `pip install -e ".[api]"
cd frontend && pnpm install && cd ..`;
	const DEV_SERVER = `cd frontend
pnpm dev`;
	const SINGLE_SERVER = `cd frontend && pnpm build && cd ..
tvdata serve --data-dir data --static-dir frontend/build`;

	const usedEndpoints = API_ENDPOINTS.filter((e) => e.usedBy).length;
	const presetCount = generatePresets().length;
	const maxImportMb = MAX_IMPORT_BYTES / 1024 / 1024;

	const FAQ = [
		{
			q: 'The dashboard is empty',
			a: 'That is expected until data exists. The backend data directory has no OHLCV captures yet. Capture some with the tvdata bars command (see Quick start), then press Refresh on the Datasets page; the backend rescans on every request, so no restart is needed. You can also use Import CSV in the top bar to explore a file without the backend.'
		},
		{
			q: 'The header says "Backend unreachable"',
			a: 'The app could not reach the API. Check that tvdata serve is running and that its port is the one the dev server forwards to (8000 by default). If you start the backend on another port, change the /api proxy target in frontend/vite.config.ts to match. Requests retry automatically a couple of times before this message appears.'
		},
		{
			q: 'A dataset is listed as invalid',
			a: 'The file failed validation, and the row shows the reason, for example missing required columns or no valid rows. It stays in the list so you can see what is wrong, but it cannot be opened. Fix the file and press Refresh.'
		},
		{
			q: 'Import CSV rejects my file',
			a: `The message names the cause: a missing required column (time, open, high, low, close, volume), no valid rows after validation, or a file larger than ${maxImportMb} MB. Column order does not matter and commas, semicolons and tabs are detected.`
		},
		{
			q: 'My filter matches nothing',
			a: 'Indicators have no value during warm-up (for example the first 13 bars of a 14-period RSI), and a missing value never satisfies a condition. Check the matched count next to the filter, and look for a red condition: unknown fields and invalid operands are reported on the row instead of being ignored. Percentile conditions rank against the whole sample, so they can also match fewer bars than you expect.'
		},
		{
			q: 'The Sentiment page shows an error',
			a: 'Your backend could not read the index from CoinMarketCap, and nothing is shown in its place. The message says why: a timeout, no internet access from the machine running the backend, or CoinMarketCap answering with an error or limiting access. Press Retry. The backend waits a minute after a failure before asking again. "This backend does not serve the Fear & Greed index" means the backend is older than the dashboard; update it and restart tvdata serve.'
		},
		{
			q: 'A chart says "Not available for this dataset"',
			a: 'The backend could not compute that section and gave the reason. The usual ones are too few bars (the return statistics need at least 30 returns) and a capture that is not intraday (activity by hour needs bars shorter than a day). Capture more data or a shorter timeframe and press Refresh on the Datasets page.'
		},
		{
			q: 'The verdict says "insufficient data"',
			a: 'No rule traded at least the minimum number of times (30 by default) on the research part of the capture, so nothing can honestly be tested or ranked. This is expected for a few weeks of hourly bars: a moving-average rule that changes position a few dozen times has too few trades for any statistic to mean something. Capture a longer history, use a shorter timeframe, or add more datasets. Lowering the minimum only makes the statistics look more certain than they are.'
		},
		{
			q: 'Why can I not read the holdout again?',
			a: 'Looking at the same data a second time, with a different rule set, turns it into training data: you would keep choosing until something looks good. The backend refuses a second read for the whole dataset, not just for the same rules. The first result is stored and shown on the page. To test further, use the bars captured after the freeze.'
		},
		{
			q: 'The Verdict numbers differ from the Research page',
			a: 'They use different fill models. Research fills at the signal bar\u2019s close with a single cost per position change; Verdict fills at the next bar\u2019s open and charges fee, spread and slippage on both sides. Verdict also leaves out the sealed holdout. Use Research to explore and Verdict to decide whether anything is worth believing.'
		},
		{
			q: 'A research run fails with a 422 error',
			a: 'The backend rejected the request. The message says why: usually a dataset that was moved or renamed since the list loaded (press Refresh on Datasets and select it again), a file that fails validation, or a parameter outside its range (cost 0 to 10,000 bps, periods per year above 0).'
		}
	] as const;
</script>

<svelte:head>
	<title>Docs · Quant Research</title>
</svelte:head>

<div class="grid grid-cols-[minmax(0,1fr)] gap-[60px]">
	<header class="grid max-w-[860px] gap-5">
		<p class="type-caption text-ink-muted">Documentation</p>
		<h1 class="type-display-lg">Docs</h1>
		<p class="max-w-[60ch] type-body-lg text-ink-muted">
			How to run the dashboard, where its data comes from, and what every filter, indicator and
			research statistic means. The reference tables are generated from the code, so they always
			match what the app does.
		</p>
		<div class="flex flex-wrap gap-2">
			<a href="#quick-start" class={buttonVariants({ variant: 'default' })}>Quick start</a>
			<a href="#api" class={buttonVariants({ variant: 'secondary' })}>API reference</a>
		</div>
	</header>

	<div class="xl:grid xl:grid-cols-[13rem_minmax(0,1fr)] xl:gap-[60px]">
		<DocsToc items={SECTIONS} {active} />

		<div class="mt-[30px] grid min-w-0 grid-cols-[minmax(0,1fr)] gap-[96px] xl:mt-0" {@attach spy}>
			<DocSection
				id="quick-start"
				title="Quick start"
				lead="Two processes: a backend that serves your captured data, and the dashboard that displays it."
			>
				<p>
					There is no sample data. The dashboard shows only what your backend serves or what you
					import yourself, so it starts empty until you have captures.
				</p>
				<h3>1. Install</h3>
				<CodeBlock label="From the repository root" code={INSTALL} />
				<h3>2. Start the backend and the dashboard</h3>
				<CodeBlock
					label="Terminal 1: backend on http://127.0.0.1:8000"
					code="tvdata serve --data-dir data"
				/>
				<CodeBlock label="Terminal 2: dashboard on http://localhost:5173" code={DEV_SERVER} />
				<p>
					Open <code>http://localhost:5173</code>. The dev server forwards <code>/api</code> to port 8000,
					so no CORS setup is needed.
				</p>
				<h3>3. Capture some data</h3>
				<CodeBlock
					label="Terminal 3, from the repository root"
					code="tvdata bars -n BINANCE:BTCUSDT,BINANCE:ETHUSDT -t 60 -b 1000 --once -o data"
				/>
				<p>
					Then press Refresh on the <a class="text-accent-blue hover:underline" href={resolve('/')}
						>Datasets</a
					>
					page. New files appear without restarting anything.
				</p>
				<h3>Single-server mode</h3>
				<p>
					For a production-style setup, build the dashboard once and let the backend host it on one
					port.
				</p>
				<CodeBlock label="Then open http://127.0.0.1:8000" code={SINGLE_SERVER} />
			</DocSection>

			<DocSection
				id="data"
				title="Data"
				lead="Two sources, and only two: captures on the backend and files you import in the tab."
			>
				<h3>Backend captures</h3>
				<p>
					The backend scans its data directory for <code
						>&lt;data-dir&gt;/&lt;symbol&gt;/&lt;timeframe&gt;.csv</code
					>
					(what <code>tvdata bars</code> writes) and for flat
					<code>&lt;data-dir&gt;/&lt;name&gt;.csv</code> files.
				</p>
				<ul>
					<li>
						The <code>.csv.meta.json</code> file next to a capture supplies its symbol and timeframe.
						Without it they come from the folder and file names.
					</li>
					<li>
						Hidden files, sidecars, other extensions, deeper folders and links that leave the data
						directory are ignored.
					</li>
					<li>
						Files are rescanned on every request, and parsed files are cached by path, size and
						modification time.
					</li>
				</ul>
				<h3>Importing a CSV</h3>
				<p>
					<strong class="font-medium text-ink">Import CSV</strong> in the top bar reads a file in your
					browser. It is held in memory only: reloading the page discards it, and it can be explored but
					not sent to a backend research run.
				</p>
				<ul>
					<li>
						Required columns: <code>time</code>, <code>open</code>, <code>high</code>,
						<code>low</code>, <code>close</code>, <code>volume</code>. Any column order; comma,
						semicolon or tab separated.
					</li>
					<li>
						Times may be Unix epochs (seconds, milliseconds, microseconds or nanoseconds), ISO
						dates, <code>YYYY/MM/DD, HH:MM:SS</code>, or TradingView's long date format. A time
						without a timezone is read as UTC.
					</li>
					<li>
						Rows with a missing or non-finite value, a price at or below zero, negative volume, a
						high below the open, close or low, or a low above them are dropped and counted.
					</li>
					<li>Duplicate timestamps keep the last row, and rows are sorted by time.</li>
					<li>Files over {maxImportMb} MB are rejected.</li>
				</ul>
				<p>
					These are the same rules the backend applies, so the same file gives the same bars either
					way. All times in the app are UTC.
				</p>
			</DocSection>

			<DocSection
				id="explorer"
				title="Explorer"
				lead="Chart a dataset, overlay indicators, filter bars and see what happened next."
			>
				<h3>Chart controls</h3>
				<ul>
					<li>
						<strong class="font-medium text-ink">Pan:</strong> drag, or use the left and right arrow keys
						(10% of the view per press), or scroll horizontally.
					</li>
					<li>
						<strong class="font-medium text-ink">Zoom:</strong> scroll the wheel (centred on the pointer),
						or press + and −.
					</li>
					<li>
						<strong class="font-medium text-ink">Jump:</strong> Home for the oldest bars, End for the
						newest.
					</li>
					<li>
						<strong class="font-medium text-ink">Reset:</strong> double-click to return to the latest
						bars.
					</li>
					<li>
						The legend above the chart shows the open, high, low, close, volume and every indicator
						value under the pointer.
					</li>
				</ul>
				<p>
					When more bars are visible than there are pixels, bars are merged per pixel column while
					keeping the open, close, high and low, so zooming out stays fast on very large captures.
				</p>
				<h3>Indicators on the chart</h3>
				<p>
					Use <strong class="font-medium text-ink">Add</strong> in the Indicators panel to search
					the
					{INDICATORS.length} available indicators. Overlays such as moving averages and Bollinger Bands
					share the price scale; oscillators such as RSI and MACD get their own pane. Each can be tuned
					with its sliders icon, hidden or removed. See
					<a class="text-accent-blue hover:underline" href="#indicators">Indicators</a> for the full list.
				</p>
				<h3>Matching bars and forward returns</h3>
				<p>
					Once a filter is active, matching bars are highlighted on the chart and listed newest
					first. Select a row to centre the chart on it.
				</p>
				<p>
					The forward-returns table measures what happened after each match: from the matching bar's
					close to the close N bars later, for each horizon you choose (up to eight, from 1 to 1,000
					bars). It shows the number of events, hit rate, mean, median, worst and best, the mean
					over all bars for comparison, the excess over that, and a t-statistic.
				</p>
				<ul>
					<li>
						Matches close together overlap, which overstates confidence. Turn on <em
							>first bar of each run only</em
						> to use one event per run of consecutive matches.
					</li>
					<li>
						Matches too recent to have a forward return still count as events but are left out of
						the statistics.
					</li>
					<li>
						Costs and slippage are not included. These are descriptive statistics, not trading
						advice.
					</li>
				</ul>
			</DocSection>

			<DocSection
				id="filters"
				title="Filters"
				lead="Build compound conditions over any price column or indicator output and watch the count update instantly."
			>
				<p>
					A filter is a tree. Each group combines its conditions with <strong
						class="font-medium text-ink">ALL</strong
					>
					(every one must match) or <strong class="font-medium text-ink">ANY</strong> (at least
					one), and can be negated with
					<strong class="font-medium text-ink">NOT</strong>. Groups nest inside groups. A condition
					compares one field to a value, a range, a bar count, or another field.
				</p>
				<ul>
					<li>
						A bar with a missing value, such as an indicator during warm-up, never satisfies a
						condition.
					</li>
					<li>
						A condition with no field chosen yet is skipped. One that cannot be evaluated, such as
						an unknown field or an invalid count, turns red with the reason and matches nothing; it
						is never silently ignored.
					</li>
					<li>Changing one condition recomputes only that condition. The others are reused.</li>
					<li>
						Indicator parameters are editable inside a condition, so <em>RSI(14)</em> can become
						<em>RSI(21)</em> without leaving the row.
					</li>
				</ul>
				<p>
					<strong class="font-medium text-ink">Presets</strong> add a ready-made condition with one
					click:
					{presetCount.toLocaleString('en-US')} of them, generated from each indicator's reference levels
					(for example "RSI crosses above 70") plus breakouts, streaks and percentile screens.
					<strong class="font-medium text-ink">Saved</strong>
					stores a named filter in this browser only.
				</p>
				<p class="text-ink">
					Percentile conditions use the whole dataset, including bars that come later, so use them
					to describe data, not to test a rule you could have traded. They are flagged wherever they
					appear.
				</p>
				{#snippet wide()}
					<h3 class="type-headline">Operator reference</h3>
					<OperatorReference />
				{/snippet}
			</DocSection>

			<DocSection
				id="indicators"
				title="Indicators"
				lead="{INDICATORS.length} indicators, every one computed in your browser from the bars on screen."
			>
				<p>
					Every indicator is calculated only from the current bar and earlier ones, never from later
					bars, and shows no value (not zero) until it has enough history. Seven of them (SMA, EMA,
					RSI, MACD, ATR, Bollinger Bands and VWAP) are checked against the backend's pandas
					implementation, including the exact bar where the first value appears.
				</p>
				<p>
					Parameters are listed with their default and allowed range; values outside the range are
					clamped rather than rejected. Indicators with several outputs, like MACD (line, signal,
					histogram), expose each output as its own filter field.
				</p>
				{#snippet wide()}
					<IndicatorReference />
				{/snippet}
			</DocSection>

			<DocSection
				id="research"
				title="Research"
				lead="Run the backend's strategy grid over your captures, then screen the results with the same filters."
			>
				<h3>Running</h3>
				<ul>
					<li>
						Select one or more backend datasets (imported files cannot be used), set the cost per
						position change in basis points, and set periods per year for annualisation, then press <strong
							class="font-medium text-ink">Run research</strong
						>.
					</li>
					<li>
						Periods per year should match the bar interval and market hours: 252 for daily stock
						bars, 365 for daily crypto, 8,760 for hourly 24/7 bars.
					</li>
				</ul>
				<h3>What is tested</h3>
				<p>
					A fixed grid of long-only rules per dataset: SMA crossovers and RSI mean-reversion entry
					and exit levels. A signal on one bar's close takes effect on the next bar, and the
					configured cost is charged on every position change. Spread, slippage, funding and
					execution limits are not modeled.
				</p>
				<h3>In-sample and forward windows</h3>
				<p>
					The first 60% of bars is reported as in-sample. The remaining 40% is split into four
					contiguous forward folds, with the rules held fixed and nothing re-fitted. Captures under
					50 bars use a single 30% holdout instead, and very short ones have no forward metrics at
					all.
				</p>
				<p class="text-ink">
					Comparing many permutations creates selection bias. Prefer strategies that stay positive
					across folds over any single best number, and treat a large drop from in-sample to forward
					as a warning sign.
				</p>
				<h3>Working with results</h3>
				<ul>
					<li>
						Click a column header to sort; missing values always sort last. Use Columns to show any
						of the available columns.
					</li>
					<li>
						Tick up to six strategies to compare their equity curves with buy-and-hold. Select a
						strategy name to see every window and each forward fold.
					</li>
				</ul>
				{#snippet wide()}
					<MetricGlossary />
				{/snippet}
			</DocSection>

			<DocSection
				id="verdict"
				title="Verdict"
				lead="Says what a dataset can and cannot support before anything is ranked, and never names a winner the data cannot back."
			>
				<p>
					Open <a
						class="text-accent-blue hover:underline"
						href={resolve('/verdict/[[dataset]]', {})}>Verdict</a
					>, pick a dataset and press
					<strong class="font-medium text-ink">Seal holdout and run verdict</strong>. The backend
					runs the same 16 fixed rules as Research, but with a stricter procedure, records every
					run, and ends in exactly one of three labels.
				</p>
				<h3>The procedure</h3>
				<ul>
					<li>
						<strong class="font-medium text-ink">Sealed holdout.</strong> The first run sets aside the
						most recent 10 to 30% of the bars (20% by default) before any analysis. They are excluded
						from every research query, including the older Research page, and cannot be read until the
						end.
					</li>
					<li>
						<strong class="font-medium text-ink">Next-open fills.</strong> A signal on a bar's close is
						filled at the next bar's open. A fee, half the spread and slippage of a multiple of ATR(14)
						are charged on both sides of every trade. Every rule is also run at 1.5&times; and 2&times;
						those costs, and the cost at which its average trade stops paying is reported.
					</li>
					<li>
						<strong class="font-medium text-ink">Trade-count gate.</strong> A rule needs a minimum number
						of trades (30 by default) before it gets a Sharpe, p-value or DSR. Below that it is marked
						"Too few trades" or "Never trades", is not ranked, and shows no statistics at all.
					</li>
					<li>
						<strong class="font-medium text-ink">Statistics for the rules that pass.</strong> A block
						bootstrap tests whether the best rule beats holding the asset for the same share of the time,
						with a stepdown so several rules can be judged together. The deflated Sharpe ratio asks whether
						a Sharpe is still above zero after trying many rules. The probability of backtest overfitting
						is shown with a warning that it is noisy at short lengths.
					</li>
					<li>
						<strong class="font-medium text-ink">Effective number of rules.</strong> Similar rules are
						one bet, not many, so the deflation uses an estimate of the independent ones, with a bootstrap
						interval because that estimate is itself uncertain.
					</li>
				</ul>
				<h3>The three labels</h3>
				<ul>
					<li>
						<strong class="font-medium text-ink">Insufficient data:</strong> no rule reached the minimum
						number of trades. Nothing is tested, ranked or concluded.
					</li>
					<li>
						<strong class="font-medium text-ink">Indistinguishable from luck:</strong> some rules traded
						enough to test, but fail the bootstrap or the deflated Sharpe, or stop paying at 1.5&times;
						costs.
					</li>
					<li>
						<strong class="font-medium text-ink">Candidate:</strong> at least one rule passes the gate,
						the bootstrap, the deflated Sharpe and the 1.5&times; cost stress. It can be frozen for one
						look at the holdout.
					</li>
				</ul>
				<h3>The ledger, the freeze and the holdout</h3>
				<ul>
					<li>
						Every run is appended to a trial ledger. N is the number of distinct rules ever tried on
						the dataset, failed runs included. It is read from the ledger, cannot be edited here,
						and does not change when only the costs change. The ledger is hash-chained, so editing
						it by hand is detectable.
					</li>
					<li>
						A candidate's rules, parameters and costs can be frozen under a hash. The holdout can
						then be read once per dataset. It is a sanity check, not a verdict, and a second read,
						even with a different rule set, is refused.
					</li>
					<li>
						After the freeze, bars captured later are the real out-of-sample record. Check them
						whenever the capture has run for a while.
					</li>
				</ul>
				<h3>Limits</h3>
				<p>
					With about a thousand hourly bars the honest answer is usually "insufficient data", and
					that is the point. Combinatorial purged cross-validation, intrabar stops, funding and
					liquidation, and per-regime analysis are not part of this version. The cost defaults are
					assumptions to replace with your venue's real fees. The older Research page fills at the
					signal bar's close, so its numbers differ from the Verdict page.
				</p>
			</DocSection>

			<DocSection
				id="charts"
				title="Charts"
				lead="Analysis your backend computes from a capture, drawn in the dashboard."
			>
				<p>
					Open <a class="text-accent-blue hover:underline" href={resolve('/charts/[[dataset]]', {})}
						>Charts</a
					>
					and pick a dataset. The numbers come from the backend, using the same code that draws the PNG
					charts from
					<code>tvdata chart</code>, so the two always agree. Imported CSV files are not available
					here because the backend cannot see them. All times are UTC.
				</p>
				<ul>
					<li>
						<strong class="font-medium text-ink">Volume profile:</strong> where trading happened by price.
						The point of control (POC) is the busiest price and the value area holds 70% of the volume.
						Choose 30, 60 or 100 price bins.
					</li>
					<li>
						<strong class="font-medium text-ink">Return distribution:</strong> a histogram of bar-to-bar
						returns against a normal curve with the same mean and spread, with VaR and CVaR at 95%. Extreme
						bars outside the plotted range are counted in the statistics and listed beneath.
					</li>
					<li>
						<strong class="font-medium text-ink">Drawdown:</strong> how far the close sits below its running
						peak, with the deepest drop, when it happened and whether it has recovered.
					</li>
					<li>
						<strong class="font-medium text-ink">Rolling volatility:</strong> the standard deviation of
						bar returns over a sliding window of 10 to 100 bars. It is per bar and not annualised.
					</li>
					<li>
						<strong class="font-medium text-ink">Activity by time of week:</strong> a weekday by UTC hour
						grid of bar range, volume or return. It needs intraday bars.
					</li>
					<li>
						<strong class="font-medium text-ink">Seasonality:</strong> average return and share of up
						bars by weekday and by hour. Short captures produce noisy patterns, so check the counts.
					</li>
					<li>
						<strong class="font-medium text-ink">Correlation:</strong> tick two to twenty datasets to
						compare their returns over the timestamps they share. It needs at least three overlapping
						returns.
					</li>
				</ul>
				<p>
					When a capture is too short, or is not intraday, a section is replaced by the reason the
					backend gave, such as "needs intraday bars", instead of an empty chart.
				</p>
			</DocSection>

			<DocSection
				id="sentiment"
				title="Sentiment"
				lead="The CMC Crypto Fear and Greed Index, fetched by your backend from CoinMarketCap with no API key."
			>
				<p>
					The index runs from 0 (extreme fear) to 100 (extreme greed) in five zones: extreme fear
					below 20, fear to 40, neutral to 60, greed to 80 and extreme greed above. The
					<a class="text-accent-blue hover:underline" href={resolve('/sentiment')}>Sentiment</a> page
					shows the current reading on a gauge, how it compares with yesterday, a week and a month ago
					and with the year's high and low, a history chart with Bitcoin's price on a second axis, the
					share of time spent in each zone, and a summary for the chosen range (30 days, 90 days, 1 year
					or all).
				</p>
				<h3>Where the data comes from</h3>
				<ul>
					<li>
						CoinMarketCap's documented Fear and Greed API needs a key. The backend instead reads the
						public endpoint that CoinMarketCap's own chart page uses, which needs none.
					</li>
					<li>
						That endpoint is not a published API. It can change, be rate limited or be withdrawn,
						and CoinMarketCap's terms apply to the data.
					</li>
					<li>
						The backend identifies itself honestly, sends no credentials and asks at most once every
						ten minutes however many tabs are open.
					</li>
					<li>
						If a refresh fails, the last good readings are shown with a notice saying when they were
						fetched. If there are none, you see the error and no reading. Nothing is ever estimated
						or filled in.
					</li>
					<li>A comparison date with no reading shows a dash rather than a guess.</li>
				</ul>
				<p>A sentiment index describes the market. It is not investment advice.</p>
			</DocSection>

			<DocSection
				id="providers"
				title="Providers"
				lead="Data from outside services, fetched by your backend. Alpha Vantage, Marketstack and Alpaca, with room for more."
			>
				<p>
					The <a
						class="text-accent-blue hover:underline"
						href={resolve('/providers/[[provider]]/[[endpoint]]', {})}>Providers</a
					> page lists everything a provider documents. Choose a provider in the dropdown, find an endpoint,
					fill in its parameters (the first example from the provider's documentation is already filled
					in) and press Fetch data. The answer is drawn as what it is: price history as candlesticks or
					lines with a summary and a table, fundamentals as statements and figures, news as articles with
					their sentiment, correlations as a matrix, and so on.
				</p>
				<h3>Your API key</h3>
				<ul>
					<li>
						Set <code>ALPHAVANTAGE_API_KEY</code>, <code>MARKETSTACK_API_KEY</code> and/or
						<code>ALPACA_API_KEY_ID</code> with <code>ALPACA_API_SECRET_KEY</code> (Alpaca needs
						both) in the backend's environment, or in a
						<code>.env</code> file in the folder you run <code>tvdata serve</code> from (or pass
						<code>--env-file</code>), and restart the backend. <code>.env.example</code> shows the format.
					</li>
					<li>
						The key (and Alpaca's secret) is read by the backend only. It is never sent to the
						browser, never returned in a response and never written to the log. Without it you can
						still browse every endpoint; Fetch data stays off and says why.
					</li>
				</ul>
				<h3>Premium</h3>
				<ul>
					<li>
						Premium endpoints are marked <strong>Premium</strong> in the list, with an orange edge, and
						can be filtered with the Free and Premium buttons. A free key is refused by them.
					</li>
					<li>
						Marketstack has subscription tiers, so its premium badge names the cheapest plan that
						includes the endpoint (<strong>Premium · Basic</strong>,
						<strong>Premium · Professional</strong>
						or <strong>Premium · Business</strong>), and the provider card lists the plans with what
						each one adds. Which plan your key has is for Marketstack to decide: a plan that lacks
						an endpoint is refused when you fetch, and this page says so and draws nothing.
					</li>
					<li>
						Alpaca has two plans, <strong>Basic</strong> and <strong>Algo Trader Plus</strong>, that
						differ in the feed, how recent the data may be and the rate limit rather than in which
						endpoints exist. Every Alpaca endpoint is therefore labelled <strong>Basic</strong>, and
						the tiers sit on what each plan unlocks: feed choices are named in the dropdown (for
						example <strong>SIP, all US exchanges · Algo Trader Plus</strong> or
						<strong>IEX · Basic</strong>), the paid ones are marked, and the end of a historical
						range carries Basic's 15-minute limit.
					</li>
					<li>
						Some choices are premium on their own. Intraday intervals below 15 minutes are marked
						<strong>Premium</strong> in the interval dropdown, and a note explains the history limit of
						each plan.
					</li>
					<li>
						Some free endpoints have premium options (for example the full history of a daily
						series). These are marked <strong>Premium option</strong> beside the parameter.
					</li>
					<li>
						When a key is not entitled, Alpha Vantage answers with made-up sample data and
						Marketstack and Alpaca with an error. This page detects both, shows the provider's own
						message and draws nothing.
					</li>
				</ul>
				<h3>Limits and honesty</h3>
				<ul>
					<li>
						Nothing is requested until you press Fetch data; opening a provider or an endpoint is
						free. Free Alpha Vantage keys allow 25 requests a day and free Marketstack keys 100 a
						month (ETF endpoints cost 20 each, which the form tells you), so identical requests are
						served from a five minute cache and only Fetch again spends a request. Alpaca limits
						calls per minute (200 on Basic) and its data is real time, so its answers are kept for
						30 seconds.
					</li>
					<li>
						Rate limits, a rejected key, an unreachable provider and an empty answer each get their
						own message. Nothing is estimated, filled in or shown in their place.
					</li>
					<li>
						Intraday times are converted from the provider's time zone to UTC, and the chart says
						so. Long tables and series are capped, and the page tells you how much was left out.
					</li>
				</ul>
				<p>
					The endpoint list is generated from the provider's documentation and kept in the
					repository; it does not scrape anything while you use the app. To add a provider, see
					<em>Data providers</em> in the README.
				</p>
			</DocSection>

			<DocSection
				id="api"
				title="API reference"
				lead="A small, read-only FastAPI service. The dashboard uses {usedEndpoints} of its {API_ENDPOINTS.length} endpoints."
			>
				<p>
					Every path starts with <code>/api</code>. Errors use FastAPI's shape:
					<code>{'{ "detail": "message" }'}</code>
					for 404 and 422 responses, and a list of field errors for invalid request bodies or query strings.
					NaN and infinite values are returned as <code>null</code>.
				</p>
				<p>
					Interactive docs with a try-it-out console are served by the backend at
					<!-- FastAPI's own pages, not SvelteKit routes: a full page load is intended. -->
					<!-- eslint-disable svelte/no-navigation-without-resolve -->
					<a class="text-accent-blue hover:underline" href="/api/docs" data-sveltekit-reload
						>/api/docs</a
					>
					(Swagger),
					<a class="text-accent-blue hover:underline" href="/api/redoc" data-sveltekit-reload
						>/api/redoc</a
					>
					(ReDoc) and
					<a class="text-accent-blue hover:underline" href="/api/openapi.json" data-sveltekit-reload
						>/api/openapi.json</a
					>
					(schema). They need the backend running, and Swagger and ReDoc load their scripts from a CDN,
					so they need an internet connection; this page does not.
					<!-- eslint-enable svelte/no-navigation-without-resolve -->
				</p>
				{#snippet wide()}
					<ApiReference />
				{/snippet}
			</DocSection>

			<DocSection
				id="troubleshooting"
				title="Troubleshooting"
				lead="The things that most often look like a bug."
			>
				<div class="grid">
					{#each FAQ as item (item.q)}
						<!-- faq-row: hairline-soft divider, 20px padding, answer in muted ink -->
						<Collapsible.Root class="group/faq border-t border-hairline-soft last:border-b">
							<Collapsible.Trigger
								class="flex w-full items-center justify-between gap-[15px] rounded-md py-5 text-left type-body text-ink"
							>
								{item.q}
								<ChevronDown
									class="size-4 shrink-0 text-ink-muted transition-transform duration-150 ease-out group-data-[state=open]/faq:rotate-180"
									aria-hidden="true"
								/>
							</Collapsible.Trigger>
							<Collapsible.Content class={cn('pb-5 type-body text-pretty text-ink-muted')}>
								{item.a}
							</Collapsible.Content>
						</Collapsible.Root>
					{/each}
				</div>
			</DocSection>
		</div>
	</div>
</div>
