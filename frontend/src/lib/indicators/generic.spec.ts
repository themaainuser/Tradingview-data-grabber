/** Properties every registered indicator must satisfy, at default and at non-default params. */
import { describe, expect, it } from 'vitest';
import { alternateParams, cloneOhlcv, emptyOhlcv, makeOhlcv, sliceOhlcv } from './fixtures';
import { INDICATORS, computeIndicator, resolveParams } from './registry';
import type { IndicatorDefinition, OhlcvColumns } from './types';

const N = 300;
const DATA = makeOhlcv(N, 11);
const COLUMNS = ['time', 'open', 'high', 'low', 'close', 'volume'] as const;

const near = (a: number, b: number, tol = 1e-9) =>
	(Number.isNaN(a) && Number.isNaN(b)) ||
	Math.abs(a - b) <= tol * Math.max(1, Math.abs(a), Math.abs(b));

const PARAM_SETS = (def: IndicatorDefinition): [string, Record<string, number>][] => [
	['default params', {}],
	['alternate params', alternateParams(def)]
];

const CASES = INDICATORS.map((def) => [def.id, def] as const);

function compareRange(
	def: IndicatorDefinition,
	a: Float64Array[],
	b: Float64Array[],
	end: number,
	label: string
) {
	for (let o = 0; o < def.outputs.length; o++) {
		for (let i = 0; i < end; i++) {
			if (!near(a[o][i], b[o][i])) {
				expect.fail(
					`${def.id}.${def.outputs[o].key} differs at bar ${i} (${label}): ${a[o][i]} vs ${b[o][i]}`
				);
			}
		}
	}
	expect(a).toHaveLength(def.outputs.length);
}

describe.each(CASES)('%s', (_id, def) => {
	describe.each(PARAM_SETS(def))('with %s', (_label, overrides) => {
		const full = computeIndicator(def, DATA, overrides);

		it('has no lookahead: a truncated series reproduces the same prefix', () => {
			for (const k of [1, 2, 3, 7, 15, 30, 55, 90, 140, 200, 299]) {
				const prefix = computeIndicator(def, sliceOhlcv(DATA, k), overrides);
				for (let o = 0; o < def.outputs.length; o++) {
					expect(prefix[o]).toHaveLength(k);
					expect(near(prefix[o][k - 1], full[o][k - 1]), `${def.outputs[o].key} at k=${k}`).toBe(
						true
					);
				}
				compareRange(def, prefix, full, k, `prefix ${k}`);
			}
		});

		it('ignores future bars: rewriting them leaves the past untouched', () => {
			const other = makeOhlcv(N, 977);
			for (const k of [40, 130, 250]) {
				const mutated = cloneOhlcv(DATA);
				for (const col of COLUMNS) mutated[col].set(other[col].subarray(k), k);
				compareRange(
					def,
					computeIndicator(def, mutated, overrides),
					full,
					k,
					`future rewritten from ${k}`
				);
			}
		});

		it('returns one finite-or-NaN Float64Array(n) per output without aliasing inputs', () => {
			expect(full).toHaveLength(def.outputs.length);
			const seen = new Set<Float64Array>();
			for (const series of full) {
				expect(series).toBeInstanceOf(Float64Array);
				expect(series).toHaveLength(N);
				expect(seen.has(series)).toBe(false);
				seen.add(series);
				for (const col of COLUMNS) expect(series).not.toBe(DATA[col]);
				expect(series.every((x) => Number.isNaN(x) || Number.isFinite(x))).toBe(true);
			}
			// Something must be computable on 300 bars at these parameters.
			expect(full.some((s) => s.some(Number.isFinite))).toBe(true);
		});

		it('handles empty and tiny inputs without throwing', () => {
			for (const n of [0, 1, 2, 3, 5]) {
				const out = computeIndicator(def, sliceOhlcv(DATA, n), overrides);
				expect(out).toHaveLength(def.outputs.length);
				for (const s of out) expect(s).toHaveLength(n);
			}
			const zeros = computeIndicator(def, emptyOhlcv(0), overrides);
			for (const s of zeros) expect(s).toHaveLength(0);
		});

		const windowKey = ['period', 'window'].includes(def.params[0]?.key) ? def.params[0].key : null;
		it.runIf(windowKey !== null)('keeps warm-up as NaN until the window fills', () => {
			const period = resolveParams(def, overrides)[windowKey!];
			const short = computeIndicator(def, sliceOhlcv(DATA, period - 1), overrides);
			for (const s of short) expect(s.every(Number.isNaN)).toBe(true);
			for (let o = 0; o < def.outputs.length; o++) {
				const idx = full[o].findIndex(Number.isFinite);
				if (idx >= 0)
					expect(idx, `${def.outputs[o].key} first value`).toBeGreaterThanOrEqual(period - 1);
			}
		});
	});

	it('recovers after non-finite inputs and never emits Infinity', () => {
		const holey = makeOhlcv(500, 21);
		holey.close[60] = NaN;
		holey.open[120] = Infinity;
		holey.high[180] = NaN;
		holey.low[240] = -Infinity;
		holey.volume[300] = NaN;
		const out = computeIndicator(def, holey);
		for (let o = 0; o < out.length; o++) {
			expect(out[o].every((x) => Number.isNaN(x) || Number.isFinite(x))).toBe(true);
			expect(Number.isFinite(out[o][499]), `${def.outputs[o].key} at last bar`).toBe(true);
			expect(Number.isFinite(out[o][450]), `${def.outputs[o].key} at bar 450`).toBe(true);
		}
	});

	it('reports all-NaN input as undefined, not as zero', () => {
		const nan = emptyOhlcv(120);
		for (const col of COLUMNS) nan[col].fill(NaN);
		for (const s of computeIndicator(def, nan)) expect(s.every(Number.isNaN)).toBe(true);
	});

	it('survives flat prices and zero volume without Infinity or throwing', () => {
		const flat: OhlcvColumns = emptyOhlcv(150);
		for (const col of ['open', 'high', 'low', 'close'] as const) flat[col].fill(100);
		flat.volume.fill(0);
		const volatileThenFlat = makeOhlcv(200, 3);
		for (let i = 100; i < 200; i++) {
			volatileThenFlat.open[i] = volatileThenFlat.high[i] = volatileThenFlat.low[i] = 100;
			volatileThenFlat.close[i] = 100;
			volatileThenFlat.volume[i] = 0;
		}
		for (const data of [flat, volatileThenFlat]) {
			for (const s of computeIndicator(def, data)) {
				expect(s.every((x) => Number.isNaN(x) || Number.isFinite(x))).toBe(true);
			}
		}
		expect(sliceOhlcv(flat, 0).close).toHaveLength(0);
	});
});
