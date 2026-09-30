/**
 * Canvas multi-series line chart on a shared time axis, used for equity-curve comparison.
 * Series are already bounded by the backend (a few hundred points), so no decimation is needed.
 */
import { createCanvasHost, type CanvasHost } from './host';
import { formatAxis, formatTime, niceTicks } from './scale';

export interface LineSeries {
	key: string;
	label: string;
	color: string;
	dashed?: boolean;
	/** Epoch seconds, ascending. */
	time: Float64Array;
	values: Float64Array;
}

export interface LineHover {
	time: number;
	values: { key: string; value: number | null }[];
}

const MARGIN = { left: 8, right: 60, top: 10, bottom: 22 };
const FONT = '11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/** Index of the last point at or before `time` (binary search), or -1. */
export function lastAtOrBefore(times: Float64Array, time: number): number {
	let lo = 0;
	let hi = times.length - 1;
	let found = -1;
	while (lo <= hi) {
		const mid = (lo + hi) >> 1;
		if (times[mid] <= time) {
			found = mid;
			lo = mid + 1;
		} else hi = mid - 1;
	}
	return found;
}

export class LineChartController {
	#host: CanvasHost;
	#canvas: HTMLCanvasElement;
	#series: readonly LineSeries[] = [];
	#hoverTime: number | null = null;
	#onHover: (hover: LineHover | null) => void;
	#cleanup: (() => void)[] = [];

	constructor(canvas: HTMLCanvasElement, onHover: (hover: LineHover | null) => void) {
		this.#canvas = canvas;
		this.#onHover = onHover;
		this.#host = createCanvasHost(canvas, (host) => this.#draw(host));
		const move = (e: Event) => this.#move(e as PointerEvent);
		const leave = () => this.#setHover(null);
		canvas.addEventListener('pointermove', move);
		canvas.addEventListener('pointerleave', leave);
		this.#cleanup.push(
			() => canvas.removeEventListener('pointermove', move),
			() => canvas.removeEventListener('pointerleave', leave)
		);
	}

	set(series: readonly LineSeries[]): void {
		this.#series = series;
		this.#host.schedule();
	}

	destroy(): void {
		for (const fn of this.#cleanup) fn();
		this.#host.destroy();
	}

	#extent(): { t0: number; t1: number; min: number; max: number } | null {
		let t0 = Infinity;
		let t1 = -Infinity;
		let min = Infinity;
		let max = -Infinity;
		for (const s of this.#series) {
			if (s.time.length === 0) continue;
			t0 = Math.min(t0, s.time[0]);
			t1 = Math.max(t1, s.time[s.time.length - 1]);
			for (const v of s.values) {
				if (v < min) min = v;
				if (v > max) max = v;
			}
		}
		if (!(t0 <= t1) || !(min <= max)) return null;
		const pad = (max - min || Math.abs(max) || 1) * 0.06;
		return { t0, t1: t1 === t0 ? t0 + 1 : t1, min: min - pad, max: max + pad };
	}

	#move(e: PointerEvent) {
		const extent = this.#extent();
		if (!extent) return;
		const rect = this.#canvas.getBoundingClientRect();
		const width = this.#host.width - MARGIN.left - MARGIN.right;
		const fraction = (e.clientX - rect.left - MARGIN.left) / width;
		this.#setHover(
			fraction < 0 || fraction > 1 ? null : extent.t0 + fraction * (extent.t1 - extent.t0)
		);
	}

	#setHover(time: number | null) {
		this.#hoverTime = time;
		this.#host.schedule();
		if (time === null) return this.#onHover(null);
		this.#onHover({
			time,
			values: this.#series.map((s) => {
				const i = lastAtOrBefore(s.time, time);
				return { key: s.key, value: i < 0 ? null : s.values[i] };
			})
		});
	}

	#draw(host: CanvasHost) {
		const { ctx } = host;
		ctx.clearRect(0, 0, host.width, host.height);
		const extent = this.#extent();
		if (!extent) return;
		const { t0, t1, min, max } = extent;
		const left = MARGIN.left;
		const width = host.width - MARGIN.left - MARGIN.right;
		const top = MARGIN.top;
		const bottom = host.height - MARGIN.bottom;
		const x = (t: number) => left + ((t - t0) / (t1 - t0)) * width;
		const y = (v: number) => bottom - ((v - min) / (max - min)) * (bottom - top);

		ctx.font = FONT;
		ctx.textBaseline = 'middle';
		const ticks = niceTicks(min, max, Math.max(2, Math.floor((bottom - top) / 42)));
		const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
		ctx.strokeStyle = host.color('--chart-grid');
		ctx.fillStyle = host.color('--chart-axis');
		ctx.textAlign = 'left';
		ctx.beginPath();
		for (const tick of ticks) {
			ctx.moveTo(left, Math.round(y(tick)) + 0.5);
			ctx.lineTo(left + width, Math.round(y(tick)) + 0.5);
		}
		ctx.stroke();
		for (const tick of ticks) ctx.fillText(formatAxis(tick, step), left + width + 6, y(tick));

		// Reference line at 1.0 = starting capital.
		if (min < 1 && max > 1) {
			ctx.save();
			ctx.setLineDash([4, 4]);
			ctx.strokeStyle = host.color('--chart-axis');
			ctx.globalAlpha = 0.5;
			ctx.beginPath();
			ctx.moveTo(left, Math.round(y(1)) + 0.5);
			ctx.lineTo(left + width, Math.round(y(1)) + 0.5);
			ctx.stroke();
			ctx.restore();
		}

		ctx.textAlign = 'center';
		const labels = Math.max(2, Math.floor(width / 110));
		const daily = t1 - t0 > 86_400 * 3;
		for (let k = 0; k < labels; k++) {
			const t = t0 + ((k + 0.5) / labels) * (t1 - t0);
			ctx.fillText(formatTime(t, !daily), x(t), bottom + 12);
		}

		ctx.lineWidth = 1.75;
		ctx.lineJoin = 'round';
		for (const s of this.#series) {
			ctx.strokeStyle = host.color(s.color);
			ctx.setLineDash(s.dashed ? [5, 4] : []);
			ctx.beginPath();
			for (let i = 0; i < s.time.length; i++) {
				if (i === 0) ctx.moveTo(x(s.time[i]), y(s.values[i]));
				else ctx.lineTo(x(s.time[i]), y(s.values[i]));
			}
			ctx.stroke();
		}
		ctx.setLineDash([]);

		if (this.#hoverTime !== null) {
			ctx.strokeStyle = host.color('--chart-axis');
			ctx.globalAlpha = 0.6;
			ctx.beginPath();
			ctx.moveTo(Math.round(x(this.#hoverTime)) + 0.5, top);
			ctx.lineTo(Math.round(x(this.#hoverTime)) + 0.5, bottom);
			ctx.stroke();
			ctx.globalAlpha = 1;
		}
	}
}
