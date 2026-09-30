/** Every indicator must handle 200,000 bars at default params inside a generous budget. */
import { afterAll, describe, expect, it } from 'vitest';
import { makeOhlcv } from './fixtures';
import { rollingMax, rollingMean, rollingRegression, rollingStd, rollingSum, wma } from './math';
import { INDICATORS, computeIndicator } from './registry';

const N = 200_000;
const BUDGET_MS = 1500;
const data = makeOhlcv(N, 2024);
const timings: { id: string; cold: number; best: number }[] = [];

afterAll(() => {
	const slowest = [...timings].sort((a, b) => b.best - a.best).slice(0, 5);
	const total = timings.reduce((sum, t) => sum + t.best, 0);
	console.info(
		`[indicators @ n=${N}] ${timings.length} indicators, total best-of-3 ${total.toFixed(0)} ms; slowest 5:\n` +
			slowest
				.map(
					(t) => `  ${t.id.padEnd(22)} best ${t.best.toFixed(1)} ms (cold ${t.cold.toFixed(1)} ms)`
				)
				.join('\n')
	);
});

/** Budget applies to the cold first run; best-of-3 only makes the printed ranking GC-robust. */
describe(`compute at n=${N}`, () => {
	it.each(INDICATORS.map((def) => [def.id, def] as const))(
		'%s finishes within budget',
		(_id, def) => {
			const samples: number[] = [];
			let out: Float64Array[] = [];
			for (let run = 0; run < 3; run++) {
				const start = performance.now();
				out = computeIndicator(def, data);
				samples.push(performance.now() - start);
			}
			timings.push({ id: def.id, cold: samples[0], best: Math.min(...samples) });
			expect(out).toHaveLength(def.outputs.length);
			expect(out[0]).toHaveLength(N);
			expect(samples[0]).toBeLessThan(BUDGET_MS);
		}
	);
});

describe('rolling primitives are independent of the window length', () => {
	const src = data.close;
	it.each([
		['rollingSum', (w: number) => rollingSum(src, w)],
		['rollingMean', (w: number) => rollingMean(src, w)],
		['rollingStd', (w: number) => rollingStd(src, w, 1)],
		['rollingMax', (w: number) => rollingMax(src, w)],
		['wma', (w: number) => wma(src, w)],
		['rollingRegression', (w: number) => rollingRegression(src, w).slope]
	] as const)('%s with a 5,000-bar window stays fast', (_name, fn) => {
		const start = performance.now();
		const out = fn(5000);
		const ms = performance.now() - start;
		expect(out).toHaveLength(N);
		// A naive O(n * w) loop would need ~1e9 operations here.
		expect(ms).toBeLessThan(400);
	});
});
