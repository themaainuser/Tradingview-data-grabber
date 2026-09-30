/**
 * Canvas price chart: candlesticks, overlay indicators, volume and stacked indicator panes.
 *
 * Performance notes:
 * - Only the visible slice is touched; when bars outnumber pixels the slice is bucketed per
 *   pixel column (`bucketCandles`, `decimateLine`), so cost is O(pixels) not O(bars).
 * - Drawing is coalesced to one animation frame and skips work while the canvas has no size.
 * - Pointer, wheel and keyboard handlers mutate a plain view object and schedule a redraw; no
 *   framework state changes on pan/zoom, only on hover when the hovered bar changes.
 */
import type { OhlcvColumns } from '$lib/indicators/types';
import { bucketCandles, decimateLine, finiteExtent } from './decimate';
import { createCanvasHost, type CanvasHost } from './host';
import { formatAxis, formatTime, isIntraday, niceTicks } from './scale';
import type { ChartPane, ChartSeries } from './types';
import {
	centerOn,
	clampView,
	indexToX,
	latestView,
	panView,
	xToIndex,
	zoomView,
	type View
} from './viewport';

export interface CandleChartInput {
	columns: OhlcvColumns;
	overlays: readonly ChartSeries[];
	panes: readonly ChartPane[];
	mask: Uint8Array | null;
	showVolume: boolean;
}

export interface CandleChartCallbacks {
	onHover(index: number | null): void;
}

const MARGIN = { left: 8, right: 68, top: 8, bottom: 22 };
const PANE_GAP = 6;
const FONT = '11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

interface PaneRect {
	top: number;
	bottom: number;
	weight: number;
}

export class CandleChartController {
	#host: CanvasHost;
	#canvas: HTMLCanvasElement;
	#input: CandleChartInput | null = null;
	#view: View = { start: 0, end: 0 };
	#hover: number | null = null;
	#pointerY = 0;
	#drag: { x: number; view: View } | null = null;
	#intraday = false;
	#callbacks: CandleChartCallbacks;
	#cleanup: (() => void)[] = [];

	constructor(canvas: HTMLCanvasElement, callbacks: CandleChartCallbacks) {
		this.#canvas = canvas;
		this.#callbacks = callbacks;
		this.#host = createCanvasHost(canvas, (host) => this.#draw(host));
		this.#listen('pointerdown', (e) => this.#pointerDown(e as PointerEvent));
		this.#listen('pointermove', (e) => this.#pointerMove(e as PointerEvent));
		this.#listen('pointerup', (e) => this.#pointerUp(e as PointerEvent));
		this.#listen('pointercancel', (e) => this.#pointerUp(e as PointerEvent));
		this.#listen('pointerleave', () => this.#setHover(null));
		this.#listen('dblclick', () => this.resetView());
		this.#listen('keydown', (e) => this.#keyDown(e as KeyboardEvent));
		// Wheel must be non-passive so page scroll can be suppressed while zooming.
		this.#listen('wheel', (e) => this.#wheel(e as WheelEvent), { passive: false });
	}

	#listen(type: string, handler: (event: Event) => void, options?: AddEventListenerOptions) {
		this.#canvas.addEventListener(type, handler, options);
		this.#cleanup.push(() => this.#canvas.removeEventListener(type, handler));
	}

	get view(): View {
		return this.#view;
	}

	/** Supplies new data. The view is kept when the dataset is unchanged, reset otherwise. */
	set(input: CandleChartInput): void {
		const previous = this.#input?.columns;
		this.#input = input;
		const length = input.columns.close.length;
		if (previous !== input.columns) {
			this.#view = latestView(length);
			this.#intraday = isIntraday(input.columns.time);
			this.#setHover(null);
		} else {
			this.#view = clampView(this.#view, length);
		}
		this.#host.schedule();
	}

	focus(index: number): void {
		if (!this.#input) return;
		this.#view = centerOn(this.#view, index, this.#input.columns.close.length);
		this.#host.schedule();
	}

	resetView(): void {
		if (!this.#input) return;
		this.#view = latestView(this.#input.columns.close.length);
		this.#host.schedule();
	}

	destroy(): void {
		for (const fn of this.#cleanup) fn();
		this.#host.destroy();
	}

	// ---- interaction ---------------------------------------------------------------------

	get #plotWidth(): number {
		return Math.max(1, this.#host.width - MARGIN.left - MARGIN.right);
	}

	#setHover(index: number | null) {
		if (index !== this.#hover) {
			this.#hover = index;
			this.#callbacks.onHover(index);
		}
		this.#host.schedule();
	}

	#pointerDown(e: PointerEvent) {
		this.#canvas.setPointerCapture(e.pointerId);
		this.#canvas.focus({ preventScroll: true });
		this.#drag = { x: e.clientX, view: this.#view };
	}

	#pointerMove(e: PointerEvent) {
		if (!this.#input) return;
		const rect = this.#canvas.getBoundingClientRect();
		const x = e.clientX - rect.left - MARGIN.left;
		this.#pointerY = e.clientY - rect.top;
		const length = this.#input.columns.close.length;
		if (this.#drag) {
			const bars =
				((this.#drag.x - e.clientX) / this.#plotWidth) *
				(this.#drag.view.end - this.#drag.view.start);
			this.#view = panView(this.#drag.view, bars, length);
		}
		const inside = x >= 0 && x <= this.#plotWidth;
		const index = inside
			? Math.min(length - 1, Math.max(0, xToIndex(x, this.#view, this.#plotWidth)))
			: null;
		this.#setHover(index);
	}

	#pointerUp(e: PointerEvent) {
		if (this.#canvas.hasPointerCapture(e.pointerId))
			this.#canvas.releasePointerCapture(e.pointerId);
		this.#drag = null;
	}

	#wheel(e: WheelEvent) {
		if (!this.#input) return;
		e.preventDefault();
		const length = this.#input.columns.close.length;
		if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
			const delta = e.shiftKey ? e.deltaY : e.deltaX;
			const bars = (delta / this.#plotWidth) * (this.#view.end - this.#view.start);
			this.#view = panView(this.#view, bars, length);
		} else {
			const rect = this.#canvas.getBoundingClientRect();
			const anchor = Math.min(
				1,
				Math.max(0, (e.clientX - rect.left - MARGIN.left) / this.#plotWidth)
			);
			this.#view = zoomView(this.#view, Math.exp(e.deltaY * 0.0015), anchor, length);
		}
		this.#host.schedule();
	}

	#keyDown(e: KeyboardEvent) {
		if (!this.#input) return;
		const length = this.#input.columns.close.length;
		const span = this.#view.end - this.#view.start;
		const actions: Record<string, () => View> = {
			ArrowLeft: () => panView(this.#view, -span * 0.1, length),
			ArrowRight: () => panView(this.#view, span * 0.1, length),
			'+': () => zoomView(this.#view, 0.8, 0.5, length),
			'=': () => zoomView(this.#view, 0.8, 0.5, length),
			'-': () => zoomView(this.#view, 1.25, 0.5, length),
			Home: () => clampView({ start: 0, end: span }, length),
			End: () => latestView(length, span)
		};
		const action = actions[e.key];
		if (!action) return;
		e.preventDefault();
		this.#view = action();
		this.#host.schedule();
	}

	// ---- drawing -------------------------------------------------------------------------

	#layout(): PaneRect[] {
		const input = this.#input!;
		const weights = [5];
		if (input.showVolume) weights.push(1.3);
		for (let i = 0; i < input.panes.length; i++) weights.push(2.2);
		const total = weights.reduce((a, b) => a + b, 0);
		const usable = this.#host.height - MARGIN.top - MARGIN.bottom - PANE_GAP * (weights.length - 1);
		let y = MARGIN.top;
		return weights.map((weight) => {
			const top = y;
			y += (weight / total) * usable;
			const rect = { top, bottom: y, weight };
			y += PANE_GAP;
			return rect;
		});
	}

	#draw(host: CanvasHost) {
		const { ctx } = host;
		ctx.clearRect(0, 0, host.width, host.height);
		const input = this.#input;
		if (!input || input.columns.close.length === 0) return;
		const view = this.#view;
		const left = MARGIN.left;
		const width = this.#plotWidth;
		const rects = this.#layout();
		ctx.font = FONT;
		ctx.textBaseline = 'middle';

		let slot = 0;
		this.#drawPricePane(host, rects[slot++], view, left, width, input);
		if (input.showVolume) this.#drawVolumePane(host, rects[slot++], view, left, width, input);
		for (const pane of input.panes)
			this.#drawIndicatorPane(host, rects[slot++], view, left, width, pane);
		this.#drawTimeAxis(host, rects[rects.length - 1].bottom, view, left, width, input.columns.time);
		this.#drawCrosshair(host, rects, view, left, width);
	}

	#grid(host: CanvasHost, rect: PaneRect, left: number, width: number, min: number, max: number) {
		const { ctx } = host;
		const ticks = niceTicks(min, max, Math.max(3, Math.floor((rect.bottom - rect.top) / 34)));
		const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
		const y = (v: number) =>
			rect.bottom - ((v - min) / (max - min || 1)) * (rect.bottom - rect.top);
		ctx.lineWidth = 1;
		ctx.strokeStyle = host.color('--chart-grid');
		ctx.fillStyle = host.color('--chart-axis');
		ctx.textAlign = 'left';
		ctx.beginPath();
		for (const tick of ticks) {
			const py = Math.round(y(tick)) + 0.5;
			ctx.moveTo(left, py);
			ctx.lineTo(left + width, py);
		}
		ctx.stroke();
		for (const tick of ticks) ctx.fillText(formatAxis(tick, step), left + width + 6, y(tick));
		return y;
	}

	#range(values: Float64Array[], view: View, fallback: [number, number]): [number, number] {
		let min = Infinity;
		let max = -Infinity;
		for (const series of values) {
			const [lo, hi] = finiteExtent(series, view.start, view.end);
			if (lo < min) min = lo;
			if (hi > max) max = hi;
		}
		if (!(min <= max)) [min, max] = fallback;
		const pad = (max - min || Math.abs(max) || 1) * 0.06;
		return [min - pad, max + pad];
	}

	#drawPricePane(
		host: CanvasHost,
		rect: PaneRect,
		view: View,
		left: number,
		width: number,
		input: CandleChartInput
	) {
		const { ctx } = host;
		const { columns, overlays, mask } = input;
		const [min, max] = this.#range(
			[columns.high, columns.low, ...overlays.map((o) => o.values)],
			view,
			[0, 1]
		);
		const y = this.#grid(host, rect, left, width, min, max);
		const barWidth = width / (view.end - view.start);
		const buckets = bucketCandles(columns, view.start, view.end, width, mask);
		const dense = barWidth < 1;
		const body = Math.max(1, Math.min(barWidth * 0.7, 14));

		ctx.save();
		ctx.beginPath();
		ctx.rect(left, rect.top, width, rect.bottom - rect.top);
		ctx.clip();

		if (mask) {
			// Filter matches are a selection state, so they take the accent blue.
			ctx.fillStyle = host.color('--accent-blue');
			ctx.globalAlpha = 0.16;
			const band = Math.max(1, dense ? 1 : barWidth);
			for (const b of buckets) {
				if (!b.flagged) continue;
				const x = dense ? left + b.x : left + indexToX(b.from, view, width) - barWidth / 2;
				ctx.fillRect(x, rect.top, band, rect.bottom - rect.top);
			}
			ctx.globalAlpha = 1;
		}

		const positive = host.color('--semantic-success');
		const negative = host.color('--gradient-coral');
		ctx.lineWidth = 1;
		for (const b of buckets) {
			const up = b.close >= b.open;
			const color = up ? positive : negative;
			ctx.strokeStyle = color;
			ctx.fillStyle = color;
			const cx = dense ? left + b.x + 0.5 : left + indexToX(b.from, view, width);
			ctx.beginPath();
			ctx.moveTo(Math.round(cx) + 0.5, y(b.high));
			ctx.lineTo(Math.round(cx) + 0.5, y(b.low));
			ctx.stroke();
			if (!dense) {
				const top = y(Math.max(b.open, b.close));
				ctx.fillRect(cx - body / 2, top, body, Math.max(1, y(Math.min(b.open, b.close)) - top));
			}
		}
		for (const series of overlays) this.#line(host, series, view, left, width, y);
		ctx.restore();
	}

	#line(
		host: CanvasHost,
		series: ChartSeries,
		view: View,
		left: number,
		width: number,
		y: (v: number) => number
	) {
		const { ctx } = host;
		const { index, value } = decimateLine(series.values, view.start, view.end, width);
		ctx.strokeStyle = host.color(series.color);
		ctx.lineWidth = 1.5;
		ctx.lineJoin = 'round';
		ctx.beginPath();
		let pen = false;
		for (let k = 0; k < index.length; k++) {
			const v = value[k];
			if (v !== v) {
				pen = false;
				continue;
			}
			const px = left + indexToX(index[k], view, width);
			if (pen) ctx.lineTo(px, y(v));
			else ctx.moveTo(px, y(v));
			pen = true;
		}
		ctx.stroke();
	}

	#drawVolumePane(
		host: CanvasHost,
		rect: PaneRect,
		view: View,
		left: number,
		width: number,
		input: CandleChartInput
	) {
		const { ctx } = host;
		const { columns } = input;
		const [, max] = finiteExtent(columns.volume, view.start, view.end);
		const top = Number.isFinite(max) && max > 0 ? max * 1.08 : 1;
		const y = this.#grid(host, rect, left, width, 0, top);
		const first = Math.max(0, Math.floor(view.start));
		const last = Math.min(columns.close.length, Math.ceil(view.end));
		const barWidth = width / (view.end - view.start);
		const positive = host.color('--semantic-success');
		const negative = host.color('--gradient-coral');
		ctx.save();
		ctx.beginPath();
		ctx.rect(left, rect.top, width, rect.bottom - rect.top);
		ctx.clip();
		ctx.globalAlpha = 0.55;
		let column = -1;
		let peak = 0;
		let up = true;
		const flush = () => {
			if (column < 0) return;
			ctx.fillStyle = up ? positive : negative;
			ctx.fillRect(left + column, y(peak), 1, rect.bottom - y(peak));
		};
		for (let i = first; i < last; i++) {
			const v = columns.volume[i];
			if (v !== v) continue;
			const isUp = columns.close[i] >= columns.open[i];
			if (barWidth >= 1) {
				ctx.fillStyle = isUp ? positive : negative;
				const w = Math.max(1, barWidth * 0.7);
				ctx.fillRect(left + indexToX(i, view, width) - w / 2, y(v), w, rect.bottom - y(v));
			} else {
				const x = Math.floor(((i - view.start) / (view.end - view.start)) * width);
				if (x !== column) {
					flush();
					column = x;
					peak = 0;
				}
				if (v >= peak) {
					peak = v;
					up = isUp;
				}
			}
		}
		if (barWidth < 1) flush();
		ctx.restore();
		this.#paneLabel(host, rect, left, 'Volume');
	}

	#drawIndicatorPane(
		host: CanvasHost,
		rect: PaneRect,
		view: View,
		left: number,
		width: number,
		pane: ChartPane
	) {
		const { ctx } = host;
		const [min, max] = this.#range(
			[...pane.series.map((s) => s.values), Float64Array.from(pane.guides)],
			view,
			[0, 1]
		);
		const y = this.#grid(host, rect, left, width, min, max);
		ctx.save();
		ctx.beginPath();
		ctx.rect(left, rect.top, width, rect.bottom - rect.top);
		ctx.clip();
		ctx.setLineDash([4, 4]);
		ctx.strokeStyle = host.color('--chart-axis');
		ctx.globalAlpha = 0.5;
		ctx.beginPath();
		for (const guide of pane.guides) {
			ctx.moveTo(left, Math.round(y(guide)) + 0.5);
			ctx.lineTo(left + width, Math.round(y(guide)) + 0.5);
		}
		ctx.stroke();
		ctx.setLineDash([]);
		ctx.globalAlpha = 1;
		const zero = y(Math.min(Math.max(0, min), max));
		for (const series of pane.series) {
			if (series.style === 'histogram') {
				const first = Math.max(0, Math.floor(view.start));
				const last = Math.min(series.values.length, Math.ceil(view.end));
				const w = Math.max(1, (width / (view.end - view.start)) * 0.7);
				ctx.fillStyle = host.color(series.color);
				ctx.globalAlpha = 0.6;
				const stride = Math.max(1, Math.floor((last - first) / width));
				for (let i = first; i < last; i += stride) {
					const v = series.values[i];
					if (v !== v) continue;
					const px = left + indexToX(i, view, width);
					ctx.fillRect(px - w / 2, Math.min(y(v), zero), w, Math.abs(y(v) - zero) || 1);
				}
				ctx.globalAlpha = 1;
			} else {
				this.#line(host, series, view, left, width, y);
			}
		}
		ctx.restore();
		this.#paneLabel(host, rect, left, pane.label);
	}

	#paneLabel(host: CanvasHost, rect: PaneRect, left: number, text: string) {
		const { ctx } = host;
		ctx.textAlign = 'left';
		// A background-coloured halo keeps the label legible where the series passes underneath.
		ctx.lineWidth = 3;
		ctx.lineJoin = 'round';
		ctx.strokeStyle = host.color('--chart-bg');
		ctx.strokeText(text, left + 6, rect.top + 10);
		ctx.fillStyle = host.color('--chart-axis');
		ctx.fillText(text, left + 6, rect.top + 10);
	}

	#drawTimeAxis(
		host: CanvasHost,
		bottom: number,
		view: View,
		left: number,
		width: number,
		time: Float64Array
	) {
		const { ctx } = host;
		ctx.fillStyle = host.color('--chart-axis');
		ctx.textAlign = 'center';
		const count = Math.max(2, Math.floor(width / 120));
		for (let k = 0; k < count; k++) {
			const index = Math.min(
				time.length - 1,
				Math.max(0, Math.floor(view.start + ((k + 0.5) / count) * (view.end - view.start)))
			);
			ctx.fillText(
				formatTime(time[index], this.#intraday),
				left + indexToX(index, view, width),
				bottom + 12
			);
		}
	}

	#drawCrosshair(host: CanvasHost, rects: PaneRect[], view: View, left: number, width: number) {
		if (this.#hover === null) return;
		const { ctx } = host;
		const x = Math.round(left + indexToX(this.#hover, view, width)) + 0.5;
		ctx.save();
		ctx.strokeStyle = host.color('--chart-axis');
		ctx.globalAlpha = 0.6;
		ctx.setLineDash([3, 3]);
		ctx.beginPath();
		ctx.moveTo(x, rects[0].top);
		ctx.lineTo(x, rects[rects.length - 1].bottom);
		const inPane = rects.some((r) => this.#pointerY >= r.top && this.#pointerY <= r.bottom);
		if (inPane) {
			ctx.moveTo(left, Math.round(this.#pointerY) + 0.5);
			ctx.lineTo(left + width, Math.round(this.#pointerY) + 0.5);
		}
		ctx.stroke();
		ctx.restore();
	}
}
