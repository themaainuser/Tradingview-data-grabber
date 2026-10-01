import { describe, expect, it } from 'vitest';
import { LINE_COLORS, populated, toCandles, toLines } from './series';
import { lineView, seriesView } from '$lib/testing/provider-fixtures';
import type { SeriesView } from '$lib/api/providers';

const line = lineView() as SeriesView;

describe('toCandles', () => {
	it('builds typed columns in time order from an OHLCV series', () => {
		const candles = toCandles(seriesView(10))!;
		expect(candles.columns.time).toHaveLength(10);
		expect(candles.columns.close[3]).toBe(103 + 0);
		expect(candles.hasVolume).toBe(true);
		expect(candles.dropped).toBe(0);
	});

	it('is not drawn as candles unless open, high, low and close are all present', () => {
		expect(toCandles(line)).toBeNull();
		const noOpen = seriesView(10);
		noOpen.series = noOpen.series.filter((s) => s.role !== 'open');
		expect(toCandles(noOpen)).toBeNull();
	});

	it('leaves out a bar with a missing price and counts it, rather than inventing a value', () => {
		const view = seriesView(10);
		view.series.find((s) => s.role === 'high')!.values[4] = null;
		const candles = toCandles(view)!;
		expect(candles.columns.time).toHaveLength(9);
		expect(candles.dropped).toBe(1);
		expect(candles.columns.time).not.toContain(view.time[4]);
		expect([...candles.columns.high].every(Number.isFinite)).toBe(true);
	});

	it('returns null when fewer than two complete bars remain', () => {
		const view = seriesView(3);
		view.series.find((s) => s.role === 'open')!.values[0] = null;
		view.series.find((s) => s.role === 'close')!.values[1] = null;
		expect(toCandles(view)).toBeNull();
	});

	it('has no volume when the series has none, or all of it is missing, and marks gaps as NaN', () => {
		const none = seriesView(6);
		none.series = none.series.filter((s) => s.role !== 'volume');
		const a = toCandles(none)!;
		expect(a.hasVolume).toBe(false);
		expect([...a.columns.volume].every(Number.isNaN)).toBe(true);
		const allNull = seriesView(6);
		allNull.series.find((s) => s.role === 'volume')!.values = allNull.time.map(() => null);
		expect(toCandles(allNull)!.hasVolume).toBe(false);
		const some = seriesView(6);
		some.series.find((s) => s.role === 'volume')!.values[2] = null;
		const c = toCandles(some)!;
		expect(c.hasVolume).toBe(true);
		expect(Number.isNaN(c.columns.volume[2])).toBe(true);
	});
});

describe('toLines', () => {
	it('puts volume on the right axis as an area when prices are present, and prices on the left', () => {
		const lines = toLines(seriesView(5));
		const volume = lines.find((l) => l.key === 'volume')!;
		expect(volume).toMatchObject({ axis: 'right', kind: 'area' });
		expect(
			lines.filter((l) => l.key !== 'volume').every((l) => l.axis === 'left' && l.kind === 'line')
		).toBe(true);
	});

	it('keeps a volume-only series on the left axis', () => {
		const view = seriesView(5);
		view.series = view.series.filter((s) => s.role === 'volume');
		expect(toLines(view)[0].axis).toBe('left');
	});

	it('cycles colours past the palette and gives every line one of them', () => {
		const view = seriesView(5);
		view.series = Array.from({ length: 7 }, (_, i) => ({
			key: `s${i}`,
			label: `S${i}`,
			values: [1, 2, 3, 4, 5],
			role: 'value' as const,
			unit: null
		}));
		const colours = toLines(view).map((l) => l.color);
		expect(colours.slice(0, 5)).toEqual([...LINE_COLORS]);
		expect(colours[5]).toBe(colours[0]);
	});

	it('shows only the requested series and puts the unit in the label', () => {
		expect(toLines(seriesView(5), ['close']).map((l) => l.key)).toEqual(['close']);
		expect(toLines(line)[0].label).toBe('SMA (USD)');
	});

	it('passes missing values through as gaps', () => {
		const view = seriesView(5);
		view.series[0].values[1] = null;
		expect(toLines(view)[0].values[1]).toBeNull();
	});
});

describe('populated', () => {
	it('lists series that carry at least one value', () => {
		const view = seriesView(4);
		view.series[0].values = [null, null, null, null];
		expect(populated(view)).toEqual(['high', 'low', 'close', 'volume']);
	});
});
