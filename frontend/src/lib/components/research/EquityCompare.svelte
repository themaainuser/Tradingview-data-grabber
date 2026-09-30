<script lang="ts">
	import LineChart from '$lib/components/app/LineChart.svelte';
	import { CHART_PALETTE } from '$lib/charts/types';
	import type { LineSeries } from '$lib/charts/line-controller';
	import type { EquityCurve } from '$lib/api/contracts';
	import { uniqueBy } from '$lib/group';
	import type { ResearchTable } from '$lib/research/columns';

	interface Props {
		table: ResearchTable;
		/** Result ids to overlay. */
		ids: readonly string[];
	}

	let { table, ids }: Props = $props();

	function toSeries(
		key: string,
		label: string,
		color: string,
		curve: EquityCurve,
		dashed = false
	): LineSeries {
		// The backend sends ISO timestamps; the chart works in epoch seconds.
		const time = new Float64Array(curve.length);
		const values = new Float64Array(curve.length);
		curve.forEach(([iso, value], i) => {
			time[i] = Date.parse(iso) / 1000;
			values[i] = value;
		});
		return { key, label, color, time, values, dashed };
	}

	const series = $derived.by(() => {
		const chosen = table.rows.filter((row) => ids.includes(row.id));
		const out: LineSeries[] = [];
		for (const row of uniqueBy(chosen, (r) => r.symbol)) {
			out.push(
				toSeries(
					`bh:${row.symbol}`,
					`${row.symbol} buy & hold`,
					'--chart-axis',
					row.benchmark_curve,
					true
				)
			);
		}
		chosen.forEach((row, i) => {
			out.push(
				toSeries(
					row.id,
					`${row.symbol} ${row.name}`,
					CHART_PALETTE[i % CHART_PALETTE.length],
					row.equity_curve
				)
			);
		});
		return out;
	});
</script>

{#if ids.length === 0}
	<p class="rounded-xl bg-canvas px-5 py-10 text-center type-body text-pretty text-ink-muted">
		Tick up to six strategies in the table to compare their net equity curves with buy-and-hold.
	</p>
{:else}
	<LineChart {series} label="Equity curves of the selected strategies compared with buy and hold" />
{/if}
