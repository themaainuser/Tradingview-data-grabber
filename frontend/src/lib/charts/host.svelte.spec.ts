import { afterEach, describe, expect, it } from 'vitest';
import LineChart from '$lib/components/app/LineChart.svelte';
import { mountChart } from '$lib/components/charts/test-utils';
import { createCanvasHost } from './host';

const root = document.documentElement;
afterEach(() => root.removeAttribute('data-theme'));

function makeCanvas() {
	const canvas = document.createElement('canvas');
	canvas.style.cssText = 'display:block;width:120px;height:60px';
	document.body.append(canvas);
	return canvas;
}
const pixel = (canvas: HTMLCanvasElement, x: number, y: number) => {
	const ratio = canvas.width / canvas.getBoundingClientRect().width;
	return [...canvas.getContext('2d')!.getImageData(x * ratio, y * ratio, 1, 1).data];
};

/** Canvas charts cannot use CSS variables directly, so they must re-resolve and repaint on a theme flip. */
describe('canvas host and the theme', () => {
	it('re-resolves token colours and redraws when data-theme changes', async () => {
		const canvas = makeCanvas();
		const seen: string[] = [];
		const host = createCanvasHost(canvas, (h) => {
			const fill = h.color('--surface-1');
			seen.push(fill);
			h.ctx.fillStyle = fill;
			h.ctx.fillRect(0, 0, h.width, h.height);
		});
		await expect.poll(() => seen.length).toBeGreaterThan(0);
		expect(seen.at(-1)).toBe('#141414');
		// Polled: a resize clears the bitmap until the next frame repaints it.
		await expect.poll(() => pixel(canvas, 5, 5)).toEqual([20, 20, 20, 255]);

		root.setAttribute('data-theme', 'light');
		await expect.poll(() => seen.at(-1)).toBe('#f0f0f0');
		await expect.poll(() => pixel(canvas, 5, 5)).toEqual([240, 240, 240, 255]);

		root.setAttribute('data-theme', 'dark');
		await expect.poll(() => pixel(canvas, 5, 5)).toEqual([20, 20, 20, 255]);
		host.destroy();
		canvas.remove();
	});

	it('does not redraw for unrelated attribute changes, nor after destroy()', async () => {
		const canvas = makeCanvas();
		let draws = 0;
		const host = createCanvasHost(canvas, () => draws++);
		/** Waits until layout-driven redraws (ResizeObserver) have gone quiet, so the count below is a baseline. */
		const settle = async () => {
			let stable = 0;
			let last = -1;
			while (stable < 4) {
				await new Promise((resolve) => setTimeout(resolve, 50));
				stable = draws === last ? stable + 1 : 0;
				last = draws;
			}
		};
		await expect.poll(() => draws).toBeGreaterThan(0);
		await settle();
		const baseline = draws;

		root.setAttribute('class', 'something-else');
		root.removeAttribute('class');
		await settle();
		expect(draws).toBe(baseline);

		host.destroy();
		root.setAttribute('data-theme', 'light');
		await settle();
		expect(draws).toBe(baseline);
		canvas.remove();
	});

	it('repaints a real chart in the new theme: ink strokes flip from light to dark', async () => {
		const time = Float64Array.from({ length: 50 }, (_, i) => 1_700_000_000 + i * 3600);
		const values = Float64Array.from({ length: 50 }, (_, i) => Math.sin(i / 6) + i / 25);
		const { host } = mountChart(
			LineChart,
			{ series: [{ key: 'a', label: 'A', color: '--chart-3', time, values }], label: 'Equity' },
			600
		);
		const canvas = host.querySelector('canvas')!;
		/** Near-white and near-black pixels: the --ink stroke in each theme (grid and axis colours sit between). */
		const strokes = () => {
			const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height);
			let white = 0;
			let black = 0;
			for (let i = 0; i < data.length; i += 4) {
				if (data[i + 3] < 250) continue;
				if (data[i] > 245 && data[i + 1] > 245 && data[i + 2] > 245) white++;
				if (data[i] < 12 && data[i + 1] < 12 && data[i + 2] < 12) black++;
			}
			return { white, black };
		};
		await expect.poll(() => strokes().white).toBeGreaterThan(20);
		expect(strokes().black).toBe(0);

		root.setAttribute('data-theme', 'light');
		await expect.poll(() => strokes().black).toBeGreaterThan(20);
		expect(strokes().white).toBe(0);

		root.setAttribute('data-theme', 'dark');
		await expect.poll(() => strokes().white).toBeGreaterThan(20);
		expect(strokes().black).toBe(0);
	});
});
