import { describe, expect, it } from 'vitest';
import { makeOhlcv } from './fixtures';
import {
	INDICATORS,
	computeIndicator,
	defaultSeriesCatalog,
	getIndicator,
	indicatorInstanceKey,
	resolveParams,
	seriesKey
} from './registry';
import { INDICATOR_CATEGORIES } from './types';

const rsi = getIndicator('rsi')!;
const macd = getIndicator('macd')!;
const ID_PATTERN = /^[a-z][a-z0-9_]*$/;

describe('registry integrity', () => {
	it('has a broad catalog', () => {
		expect(INDICATORS.length).toBeGreaterThanOrEqual(70);
		const covered = new Set(INDICATORS.map((d) => d.category));
		expect([...covered].sort()).toEqual([...INDICATOR_CATEGORIES].sort());
	});

	it('has unique, well-formed ids and getIndicator resolves each one', () => {
		const ids = INDICATORS.map((d) => d.id);
		expect(new Set(ids).size).toBe(ids.length);
		for (const def of INDICATORS) {
			expect(def.id).toMatch(ID_PATTERN);
			expect(getIndicator(def.id)).toBe(def);
		}
		expect(getIndicator('nope')).toBeUndefined();
	});

	it('is ordered by category then name', () => {
		const rank = (c: string) =>
			INDICATOR_CATEGORIES.indexOf(c as (typeof INDICATOR_CATEGORIES)[number]);
		for (let i = 1; i < INDICATORS.length; i++) {
			const a = INDICATORS[i - 1];
			const b = INDICATORS[i];
			const ordered =
				rank(a.category) < rank(b.category) || (a.category === b.category && a.name <= b.name);
			expect(ordered, `${a.id} before ${b.id}`).toBe(true);
		}
	});

	it('has complete metadata for every definition', () => {
		for (const def of INDICATORS) {
			expect(def.name.trim(), def.id).not.toBe('');
			expect(def.short.trim(), def.id).not.toBe('');
			expect(def.description.trim().length, def.id).toBeGreaterThan(15);
			expect(def.description, def.id).toMatch(/\.$/);
			expect(INDICATOR_CATEGORIES, def.id).toContain(def.category);
			expect(['price', 'separate'], def.id).toContain(def.pane);
			expect(typeof def.compute).toBe('function');
			expect(def.outputs.length, def.id).toBeGreaterThan(0);
		}
	});

	it('has unique output keys and unique param keys per indicator', () => {
		for (const def of INDICATORS) {
			const outputs = def.outputs.map((o) => o.key);
			expect(new Set(outputs).size, def.id).toBe(outputs.length);
			for (const o of def.outputs) expect(o.label.trim(), def.id).not.toBe('');
			const params = def.params.map((p) => p.key);
			expect(new Set(params).size, def.id).toBe(params.length);
		}
	});

	it('only declares guides on separate panes, with finite levels', () => {
		for (const def of INDICATORS) {
			if (def.guides === undefined) continue;
			expect(def.pane, def.id).toBe('separate');
			expect(def.guides.length, def.id).toBeGreaterThan(0);
			for (const g of def.guides) expect(Number.isFinite(g)).toBe(true);
		}
	});

	it('has sane parameter specs: min <= default <= max, positive step, integer sanity', () => {
		for (const def of INDICATORS) {
			for (const spec of def.params) {
				const where = `${def.id}.${spec.key}`;
				expect(spec.label.trim(), where).not.toBe('');
				expect(spec.min, where).toBeLessThanOrEqual(spec.default);
				expect(spec.default, where).toBeLessThanOrEqual(spec.max);
				expect(spec.step, where).toBeGreaterThan(0);
				expect(spec.step, where).toBeLessThanOrEqual(spec.max - spec.min);
				if (spec.integer) {
					for (const v of [spec.min, spec.default, spec.max, spec.step]) {
						expect(Number.isInteger(v), `${where} = ${v}`).toBe(true);
					}
				}
				// Windows and periods must never reach zero or below.
				if (/period|window|span|lookback|warmup|lag/i.test(spec.key)) {
					expect(spec.min, where).toBeGreaterThanOrEqual(1);
				}
			}
		}
	});
});

describe('resolveParams', () => {
	it('fills defaults', () => {
		expect(resolveParams(rsi)).toEqual({ period: 14 });
		expect(resolveParams(macd, {})).toEqual({ fast: 12, slow: 26, signal: 9 });
	});

	it('clamps out-of-range and infinite values into [min, max]', () => {
		const spec = rsi.params[0];
		expect(resolveParams(rsi, { period: -5 }).period).toBe(spec.min);
		expect(resolveParams(rsi, { period: 1e9 }).period).toBe(spec.max);
		expect(resolveParams(rsi, { period: Infinity }).period).toBe(spec.max);
		expect(resolveParams(rsi, { period: -Infinity }).period).toBe(spec.min);
	});

	it('falls back to the default for missing, NaN or non-numeric values', () => {
		for (const bad of [undefined, null, NaN, 'abc', '', {}, [], true]) {
			expect(resolveParams(rsi, { period: bad }).period).toBe(14);
		}
		expect(resolveParams(rsi, { period: '21' }).period).toBe(21);
	});

	it('rounds integer params and keeps fractional ones', () => {
		expect(resolveParams(rsi, { period: 13.6 }).period).toBe(14);
		expect(resolveParams(rsi, { period: 2.4 }).period).toBe(2);
		const bb = getIndicator('bollinger')!;
		expect(resolveParams(bb, { mult: 2.35 }).mult).toBe(2.35);
		expect(resolveParams(bb, { period: 19.5 }).period).toBe(20);
	});

	it('drops unknown keys and never throws on hostile input', () => {
		const out = resolveParams(rsi, {
			period: 10,
			bogus: 1,
			__proto__: { period: 99 },
			toString: 5
		});
		expect(out).toEqual({ period: 10 });
		for (const def of INDICATORS) {
			expect(() => resolveParams(def, null as never)).not.toThrow();
			expect(() => resolveParams(def, 5 as never)).not.toThrow();
			const hostile = Object.fromEntries(def.params.map((p) => [p.key, NaN]));
			expect(resolveParams(def, hostile)).toEqual(resolveParams(def));
		}
	});

	it('always yields params inside their bounds for extreme inputs', () => {
		for (const def of INDICATORS) {
			for (const extreme of [-1e300, -1, 0, 0.5, 1e300, Infinity]) {
				const overrides = Object.fromEntries(def.params.map((p) => [p.key, extreme]));
				const out = resolveParams(def, overrides);
				for (const spec of def.params) {
					expect(out[spec.key]).toBeGreaterThanOrEqual(spec.min);
					expect(out[spec.key]).toBeLessThanOrEqual(spec.max);
					if (spec.integer) expect(Number.isInteger(out[spec.key])).toBe(true);
				}
			}
		}
	});
});

describe('keys and catalog', () => {
	it('builds deterministic, order-independent instance keys', () => {
		expect(indicatorInstanceKey('rsi', { period: 14 })).toBe('rsi(period=14)');
		expect(indicatorInstanceKey('rsi', {})).toBe('rsi(period=14)');
		expect(indicatorInstanceKey('rsi', { period: 13.6 })).toBe('rsi(period=14)');
		const a = indicatorInstanceKey('macd', { fast: 5, signal: 3, slow: 8 });
		const b = indicatorInstanceKey('macd', { slow: 8, fast: 5, signal: 3 });
		expect(a).toBe(b);
		expect(a).toBe('macd(fast=5,signal=3,slow=8)');
		expect(indicatorInstanceKey('obv', {})).toBe('obv()');
		expect(indicatorInstanceKey('rsi', { period: 14, junk: 3 })).toBe('rsi(period=14)');
	});

	it('keeps finite numeric params for unknown ids, sorted', () => {
		expect(indicatorInstanceKey('custom', { b: 2, a: 1, c: NaN, d: 'x' })).toBe('custom(a=1,b=2)');
	});

	it('builds series keys', () => {
		expect(seriesKey('rsi', { period: 14 }, 'value')).toBe('rsi(period=14).value');
		expect(seriesKey('bollinger', undefined, 'upper')).toBe('bollinger(mult=2,period=20).upper');
	});

	it('lists every output at default params with unique keys', () => {
		const catalog = defaultSeriesCatalog();
		const expected = INDICATORS.reduce((n, d) => n + d.outputs.length, 0);
		expect(catalog).toHaveLength(expected);
		expect(new Set(catalog.map((c) => c.key)).size).toBe(catalog.length);
		const entry = catalog.find((c) => c.key === 'rsi(period=14).value');
		expect(entry).toMatchObject({
			id: 'rsi',
			name: 'Relative Strength Index',
			category: 'Momentum',
			outputKey: 'value',
			pane: 'separate'
		});
		for (const c of catalog) {
			const def = getIndicator(c.id)!;
			expect(c.pane).toBe(def.pane);
			expect(def.outputs.some((o) => o.key === c.outputKey && o.label === c.outputLabel)).toBe(
				true
			);
		}
	});

	it('returns a fresh array so callers cannot corrupt the cache', () => {
		const first = defaultSeriesCatalog();
		first.length = 0;
		expect(defaultSeriesCatalog().length).toBeGreaterThan(0);
	});
});

describe('computeIndicator', () => {
	const data = makeOhlcv(120, 5);

	it('resolves params before computing', () => {
		const viaOverrides = computeIndicator(rsi, data, { period: 1e9 });
		const explicit = rsi.compute(data, resolveParams(rsi, { period: 1e9 }));
		expect(viaOverrides[0]).toEqual(explicit[0]);
		expect(computeIndicator(rsi, data, { period: NaN })[0]).toEqual(computeIndicator(rsi, data)[0]);
	});

	it('returns one Float64Array(n) per output for every indicator', () => {
		for (const def of INDICATORS) {
			const out = computeIndicator(def, data);
			expect(out, def.id).toHaveLength(def.outputs.length);
			for (const series of out) {
				expect(series).toBeInstanceOf(Float64Array);
				expect(series, def.id).toHaveLength(data.close.length);
			}
		}
	});
});
