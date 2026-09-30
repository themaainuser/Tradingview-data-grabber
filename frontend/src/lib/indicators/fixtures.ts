/**
 * Deterministic synthetic OHLCV for tests and benchmarks only (never imported by app code).
 *
 * Only IEEE-754 add/multiply/floor are used after the integer PRNG, so the exact same series can
 * be reproduced in Python (see the golden values in `backend-parity.spec.ts`).
 */
import type { IndicatorDefinition, OhlcvColumns } from './types';

/** mulberry32: 32-bit seeded PRNG returning floats in [0, 1). */
export function mulberry32(seed: number): () => number {
	let a = seed | 0;
	return () => {
		a = (a + 0x6d2b79f5) | 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/** `spread` scales every random shock (1 reproduces the pandas-golden series exactly). */
export function makeOhlcv(n: number, seed = 42, spread = 1): OhlcvColumns {
	const rand = mulberry32(seed);
	const data: OhlcvColumns = {
		time: new Float64Array(n),
		open: new Float64Array(n),
		high: new Float64Array(n),
		low: new Float64Array(n),
		close: new Float64Array(n),
		volume: new Float64Array(n)
	};
	let prev = 100;
	for (let i = 0; i < n; i++) {
		const u1 = rand();
		const u2 = rand();
		const u3 = rand();
		const u4 = rand();
		const u5 = rand();
		// Mild linear mean reversion keeps long series near 100.
		const close = prev * (1 + (u1 - 0.5) * (0.04 * spread) - 0.0005 * (prev / 100 - 1));
		const open = prev * (1 + (u2 - 0.5) * (0.01 * spread));
		data.time[i] = 1_700_000_000 + i * 60;
		data.open[i] = open;
		data.high[i] = Math.max(open, close) * (1 + u3 * (0.01 * spread));
		data.low[i] = Math.min(open, close) * (1 - u4 * (0.01 * spread));
		data.close[i] = close;
		data.volume[i] = 1000 + Math.floor(u5 * 9000);
		prev = close;
	}
	return data;
}

export function sliceOhlcv(d: OhlcvColumns, end: number): OhlcvColumns {
	return {
		time: d.time.slice(0, end),
		open: d.open.slice(0, end),
		high: d.high.slice(0, end),
		low: d.low.slice(0, end),
		close: d.close.slice(0, end),
		volume: d.volume.slice(0, end)
	};
}

export function cloneOhlcv(d: OhlcvColumns): OhlcvColumns {
	return sliceOhlcv(d, d.close.length);
}

export function emptyOhlcv(n: number): OhlcvColumns {
	return {
		time: new Float64Array(n),
		open: new Float64Array(n),
		high: new Float64Array(n),
		low: new Float64Array(n),
		close: new Float64Array(n),
		volume: new Float64Array(n)
	};
}

/** A second valid parameter set: each param halved (or doubled when halving hits the default). */
export function alternateParams(def: IndicatorDefinition): Record<string, number> {
	const out: Record<string, number> = {};
	for (const spec of def.params) {
		const clampTo = (v: number) => Math.min(spec.max, Math.max(spec.min, v));
		const scaled = (k: number) =>
			clampTo(spec.integer ? Math.round(spec.default * k) : spec.default * k);
		const half = scaled(0.5);
		out[spec.key] = half === spec.default ? scaled(2) : half;
	}
	return out;
}
