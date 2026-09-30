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
				id="api"
				title="API reference"
				lead="A small, read-only FastAPI service. The dashboard uses three of its five endpoints."
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
