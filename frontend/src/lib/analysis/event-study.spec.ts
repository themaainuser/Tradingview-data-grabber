import { describe, expect, it } from 'vitest';
import { eventStudy, onsetMask } from './event-study';

const close = Float64Array.from([100, 110, 99, 108.9, 120, 90]);

describe('onsetMask', () => {
	it('keeps only the first bar of each run', () => {
		expect(Array.from(onsetMask(Uint8Array.from([1, 1, 0, 1, 0, 0, 1, 1])))).toEqual([
			1, 0, 0, 1, 0, 0, 1, 0
		]);
	});
});

describe('eventStudy', () => {
	it('computes forward-return statistics for matched bars', () => {
		const mask = Uint8Array.from([1, 0, 1, 0, 0, 0]);
		const { events, horizons } = eventStudy(close, mask, [1]);
		expect(events).toBe(2);
		const h = horizons[0];
		// bar 0: 110/100-1 = +10%, bar 2: 108.9/99-1 = +10%
		expect(h.n).toBe(2);
		expect(h.mean).toBeCloseTo(0.1);
		expect(h.hitRate).toBe(1);
		expect(h.median).toBeCloseTo(0.1);
		expect(h.std).toBeCloseTo(0, 10);
	});

	it('reports the unconditional baseline and excess', () => {
		const mask = Uint8Array.from([1, 0, 0, 0, 0, 0]);
		const h = eventStudy(close, mask, [1]).horizons[0];
		const all = [110 / 100, 99 / 110, 108.9 / 99, 120 / 108.9, 90 / 120].map((v) => v - 1);
		const baseline = all.reduce((a, b) => a + b, 0) / all.length;
		expect(h.baselineMean).toBeCloseTo(baseline);
		expect(h.excessMean).toBeCloseTo(h.mean! - baseline);
		expect(h.tStat).toBeNull();
	});

	it('excludes bars too recent for the horizon but still counts them as events', () => {
		const mask = Uint8Array.from([0, 0, 0, 0, 1, 1]);
		const { events, horizons } = eventStudy(close, mask, [1, 3]);
		expect(events).toBe(2);
		expect(horizons[0].n).toBe(1);
		expect(horizons[1].n).toBe(0);
		expect(horizons[1].mean).toBeNull();
	});

	it('supports onset-only de-clustering', () => {
		const mask = Uint8Array.from([1, 1, 1, 0, 0, 0]);
		expect(eventStudy(close, mask, [1], { onsetOnly: true }).events).toBe(1);
	});

	it('returns empty statistics when no filter is active or nothing matches', () => {
		expect(eventStudy(close, null, [1]).events).toBe(0);
		expect(eventStudy(close, new Uint8Array(6), [1]).horizons[0].n).toBe(0);
	});
});
