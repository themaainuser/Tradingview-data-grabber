import { describe, expect, it } from 'vitest';
import { bucketCandles, decimateLine, finiteExtent } from './decimate';
import { formatAxis, formatTime, niceTicks } from './scale';
import { centerOn, clampView, indexToX, latestView, panView, xToIndex, zoomView } from './viewport';

const f = (...v: number[]) => Float64Array.from(v);

describe('viewport', () => {
	it('clamps to the data and keeps a minimum span', () => {
		expect(clampView({ start: -10, end: 3 }, 100)).toEqual({ start: 0, end: 13 });
		expect(clampView({ start: 10, end: 11 }, 100)).toEqual({ start: 10, end: 15 });
		expect(clampView({ start: 90, end: 200 }, 100)).toEqual({ start: 0, end: 100 });
		expect(clampView({ start: 0, end: 10 }, 0)).toEqual({ start: 0, end: 0 });
		expect(clampView({ start: NaN, end: NaN }, 1000).end).toBe(1000);
	});

	it('shows the latest bars by default', () => {
		expect(latestView(1000, 240)).toEqual({ start: 760, end: 1000 });
		expect(latestView(50, 240)).toEqual({ start: 0, end: 50 });
	});

	it('zooms about the anchor without moving the pivot bar', () => {
		const view = { start: 100, end: 200 };
		const zoomed = zoomView(view, 0.5, 0.25, 1000);
		expect(zoomed.end - zoomed.start).toBe(50);
		expect(zoomed.start + 50 * 0.25).toBeCloseTo(125);
	});

	it('pans, centres and converts coordinates both ways', () => {
		expect(panView({ start: 10, end: 20 }, 5, 100)).toEqual({ start: 15, end: 25 });
		expect(panView({ start: 10, end: 20 }, 500, 100)).toEqual({ start: 90, end: 100 });
		const centred = centerOn({ start: 0, end: 10 }, 50, 100);
		expect((centred.start + centred.end) / 2).toBeCloseTo(50.5);
		const view = { start: 10, end: 20 };
		expect(xToIndex(indexToX(14, view, 500), view, 500)).toBe(14);
	});
});

describe('scale', () => {
	it('produces nice ticks inside the range', () => {
		expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
		expect(niceTicks(0.1, 0.5, 4).every((t) => t >= 0.1 && t <= 0.5 + 1e-9)).toBe(true);
		expect(niceTicks(5, 5)).toEqual([5]);
		expect(niceTicks(NaN, 5)).toEqual([]);
	});

	it('formats axis values and UTC times', () => {
		expect(formatAxis(1234.5, 1)).toBe('1,235');
		expect(formatAxis(0.25, 0.05)).toBe('0.25');
		expect(formatAxis(2_500_000, 1)).toBe('2.5M');
		expect(formatTime(Date.UTC(2026, 0, 2, 3, 4) / 1000, true)).toBe('2026-01-02 03:04');
		expect(formatTime(NaN, false)).toBe('');
	});
});

describe('decimation', () => {
	const ohlc = {
		open: f(1, 2, 3, 4),
		high: f(2, 3, 4, 5),
		low: f(0, 1, 2, 3),
		close: f(1.5, 2.5, 3.5, 4.5)
	};

	it('keeps one bucket per bar when there is room', () => {
		const buckets = bucketCandles(ohlc, 0, 4, 400, null);
		expect(buckets.map((b) => b.x)).toEqual([0, 1, 2, 3]);
	});

	it('collapses crowded bars into pixel columns preserving extremes and the mask', () => {
		const buckets = bucketCandles(ohlc, 0, 4, 2, Uint8Array.from([0, 1, 0, 0]));
		expect(buckets).toHaveLength(2);
		expect(buckets[0]).toMatchObject({
			open: 1,
			high: 3,
			low: 0,
			close: 2.5,
			flagged: true,
			from: 0,
			to: 1
		});
		expect(buckets[1]).toMatchObject({ open: 3, high: 5, low: 2, close: 4.5, flagged: false });
	});

	it('skips bars with missing prices instead of drawing zeros', () => {
		const gap = { ...ohlc, close: f(1.5, NaN, 3.5, 4.5) };
		expect(bucketCandles(gap, 0, 4, 400, null)).toHaveLength(3);
	});

	it('keeps line spikes when decimating and preserves gaps', () => {
		const values = new Float64Array(1000).fill(1);
		values[500] = 99;
		values[600] = NaN;
		const { index, value } = decimateLine(values, 0, 1000, 100);
		expect(value).toContain(99);
		expect(index.length).toBeLessThan(400);
		expect(value.some(Number.isNaN)).toBe(true);
	});

	it('returns every point for short lines and finds finite extents', () => {
		expect(decimateLine(f(1, 2, 3), 0, 3, 100).index).toEqual([0, 1, 2]);
		expect(finiteExtent(f(NaN, 3, 1, NaN), 0, 4)).toEqual([1, 3]);
		expect(finiteExtent(f(NaN), 0, 1).every(Number.isNaN)).toBe(true);
	});
});
