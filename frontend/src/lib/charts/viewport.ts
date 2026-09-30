/** Pure viewport maths for the canvas charts: a window `[start, end)` over bar indexes. */

export interface View {
	/** First visible bar (fractional while panning). */
	start: number;
	/** One past the last visible bar. */
	end: number;
}

export const MIN_VISIBLE_BARS = 5;

export function clampView(view: View, length: number): View {
	if (length <= 0) return { start: 0, end: 0 };
	const minSpan = Math.min(MIN_VISIBLE_BARS, length);
	let span = Math.min(Math.max(view.end - view.start, minSpan), length);
	let start = Math.max(0, Math.min(view.start, length - span));
	if (!Number.isFinite(start) || !Number.isFinite(span)) {
		span = Math.min(length, 200);
		start = length - span;
	}
	return { start, end: start + span };
}

/** Default window: the most recent `bars` bars. */
export function latestView(length: number, bars = 240): View {
	const span = Math.min(length, bars);
	return { start: length - span, end: length };
}

/** Zooms about `anchor` (0..1 across the plot); factor < 1 zooms in. */
export function zoomView(view: View, factor: number, anchor: number, length: number): View {
	const span = view.end - view.start;
	const pivot = view.start + span * anchor;
	const nextSpan = span * factor;
	return clampView(
		{ start: pivot - nextSpan * anchor, end: pivot + nextSpan * (1 - anchor) },
		length
	);
}

/** Pans by a number of bars (positive = towards newer data). */
export function panView(view: View, bars: number, length: number): View {
	return clampView({ start: view.start + bars, end: view.end + bars }, length);
}

/** Centres the view on a bar, keeping the current zoom. */
export function centerOn(view: View, index: number, length: number): View {
	const span = view.end - view.start;
	return clampView({ start: index + 0.5 - span / 2, end: index + 0.5 + span / 2 }, length);
}

export const indexToX = (index: number, view: View, width: number): number =>
	((index + 0.5 - view.start) / (view.end - view.start)) * width;

export const xToIndex = (x: number, view: View, width: number): number =>
	Math.floor(view.start + (x / width) * (view.end - view.start));
