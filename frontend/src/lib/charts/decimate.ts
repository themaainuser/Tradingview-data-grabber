/**
 * Level-of-detail reduction. When more bars than pixels are visible, drawing each bar wastes
 * time and produces mush, so the visible range is collapsed to one bucket per pixel column while
 * keeping the information a trader reads: first/last price and the high/low extremes.
 */

export interface CandleBucket {
	/** Pixel column (0-based) the bucket is drawn in. */
	x: number;
	open: number;
	high: number;
	low: number;
	close: number;
	/** Index range covered `[from, to]`, inclusive. */
	from: number;
	to: number;
	/** True when any bar in the bucket passes the filter mask. */
	flagged: boolean;
}

export interface CandleInput {
	open: Float64Array;
	high: Float64Array;
	low: Float64Array;
	close: Float64Array;
}

/**
 * Buckets the visible bars. Returns one bucket per bar when there is room, otherwise one per
 * pixel column. Bars with missing OHLC are skipped rather than drawn as zeros.
 */
export function bucketCandles(
	data: CandleInput,
	start: number,
	end: number,
	width: number,
	mask: Uint8Array | null
): CandleBucket[] {
	const first = Math.max(0, Math.floor(start));
	const last = Math.min(data.close.length, Math.ceil(end));
	const span = end - start;
	const barsPerPixel = span / Math.max(1, width);
	const buckets: CandleBucket[] = [];
	if (span <= 0) return buckets;
	const dense = barsPerPixel > 1;
	let current: CandleBucket | null = null;
	for (let i = first; i < last; i++) {
		const o = data.open[i];
		const h = data.high[i];
		const l = data.low[i];
		const c = data.close[i];
		if (!(o === o && h === h && l === l && c === c)) continue;
		const flagged = mask !== null && mask[i] === 1;
		const x = Math.floor(((i - start) / span) * width);
		if (dense && current && current.x === x) {
			if (h > current.high) current.high = h;
			if (l < current.low) current.low = l;
			current.close = c;
			current.to = i;
			current.flagged ||= flagged;
		} else {
			current = { x: dense ? x : i, open: o, high: h, low: l, close: c, from: i, to: i, flagged };
			buckets.push(current);
		}
	}
	return buckets;
}

/** Min/max of `values` over `[from, to)` ignoring NaN; NaN bounds when nothing is finite. */
export function finiteExtent(values: Float64Array, from: number, to: number): [number, number] {
	let min = Infinity;
	let max = -Infinity;
	const a = Math.max(0, Math.floor(from));
	const b = Math.min(values.length, Math.ceil(to));
	for (let i = a; i < b; i++) {
		const v = values[i];
		if (v < min) min = v;
		if (v > max) max = v;
	}
	return min <= max ? [min, max] : [NaN, NaN];
}

/**
 * Reduces a line to at most ~2 points per pixel column (column minimum then maximum) so spikes
 * survive. Returns index/value pairs in draw order; gaps (NaN) are preserved as NaN values.
 */
export function decimateLine(
	values: Float64Array,
	start: number,
	end: number,
	width: number
): { index: number[]; value: number[] } {
	const first = Math.max(0, Math.floor(start));
	const last = Math.min(values.length, Math.ceil(end));
	const index: number[] = [];
	const value: number[] = [];
	const span = end - start;
	if (span <= 0) return { index, value };
	if (span <= width * 2) {
		for (let i = first; i < last; i++) {
			index.push(i);
			value.push(values[i]);
		}
		return { index, value };
	}
	let column = -1;
	let minI = -1;
	let maxI = -1;
	const flush = () => {
		if (minI < 0) return;
		const pair = minI <= maxI ? [minI, maxI] : [maxI, minI];
		for (const i of minI === maxI ? [minI] : pair) {
			index.push(i);
			value.push(values[i]);
		}
	};
	for (let i = first; i < last; i++) {
		const v = values[i];
		const x = Math.floor(((i - start) / span) * width);
		if (x !== column) {
			flush();
			column = x;
			minI = maxI = -1;
		}
		if (v !== v) {
			flush();
			index.push(i);
			value.push(NaN);
			minI = maxI = -1;
			continue;
		}
		if (minI < 0 || v < values[minI]) minI = i;
		if (maxI < 0 || v > values[maxI]) maxI = i;
	}
	flush();
	return { index, value };
}
