/**
 * Adapters from a provider series view to the chart components' inputs. Nothing is invented: a bar
 * missing any of open/high/low/close is left out of the candles, and missing line values stay gaps.
 */
import type { AreaSeries } from '$lib/components/charts/types';
import type { OhlcvColumns } from '$lib/indicators/types';
import type { SeriesView } from '$lib/api/providers';

/** Line colours, cycled when a response has more series than colours. */
export const LINE_COLORS = [
	'var(--chart-1)',
	'var(--chart-2)',
	'var(--chart-3)',
	'var(--chart-4)',
	'var(--chart-5)'
] as const;

const column = (view: SeriesView, role: string) => view.series.find((s) => s.role === role);

export interface Candles {
	columns: OhlcvColumns;
	hasVolume: boolean;
	/** Bars dropped because a price was missing. */
	dropped: number;
}

/** Candles when the view carries open, high, low and close; null otherwise. */
export function toCandles(view: SeriesView): Candles | null {
	const open = column(view, 'open');
	const high = column(view, 'high');
	const low = column(view, 'low');
	const close = column(view, 'close');
	if (!open || !high || !low || !close) return null;
	const volume = column(view, 'volume');
	const keep: number[] = [];
	for (let i = 0; i < view.time.length; i++) {
		if ([open, high, low, close].every((s) => s.values[i] !== null)) keep.push(i);
	}
	if (keep.length < 2) return null;
	const pick = (values: readonly (number | null)[] | undefined) =>
		Float64Array.from(keep, (i) =>
			values?.[i] === null || values?.[i] === undefined ? Number.NaN : values[i]
		);
	const columns: OhlcvColumns = {
		time: Float64Array.from(keep, (i) => view.time[i]),
		open: pick(open.values),
		high: pick(high.values),
		low: pick(low.values),
		close: pick(close.values),
		volume: pick(volume?.values)
	};
	return {
		columns,
		hasVolume: !!volume && columns.volume.some((v) => Number.isFinite(v)),
		dropped: view.time.length - keep.length
	};
}

/**
 * Line series for the area chart. Volume sits on the right axis as an area so its scale does not
 * flatten the prices; everything else shares the left axis.
 */
export function toLines(view: SeriesView, only?: readonly string[]): AreaSeries[] {
	let colour = 0;
	return view.series
		.filter((s) => !only || only.includes(s.key))
		.map((s) => {
			const isVolume = s.role === 'volume' && view.series.some((o) => o.role !== 'volume');
			return {
				key: s.key,
				label: s.unit ? `${s.label} (${s.unit})` : s.label,
				color: isVolume ? 'var(--ink-muted)' : LINE_COLORS[colour++ % LINE_COLORS.length],
				values: s.values,
				axis: isVolume ? 'right' : 'left',
				kind: isVolume ? 'area' : 'line'
			} satisfies AreaSeries;
		});
}

/** The columns offered as toggles: OHLC bars are one chart, so only the other columns are listed. */
export const selectableKeys = (view: SeriesView): string[] => view.series.map((s) => s.key);

/** Series that carry at least one value (an all-null column would draw nothing). */
export const populated = (view: SeriesView): string[] =>
	view.series.filter((s) => s.values.some((v) => v !== null)).map((s) => s.key);
