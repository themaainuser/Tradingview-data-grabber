import { describe, expect, it } from 'vitest';
import { defaultSeriesCatalog, INDICATORS } from '$lib/indicators';
import { createEvaluator } from '$lib/filters/engine';
import { newGroup } from '$lib/filters/tree';
import { BarSource } from './bar-source';
import { createExplorerCatalog } from './catalog';
import { fieldLabel, fieldOptions, isKnownField, makeFieldKey, parseFieldKey } from './fields';
import { generatePresets } from './presets';

function columns(n = 400) {
	let seed = 9;
	const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
	const c = {
		time: new Float64Array(n),
		open: new Float64Array(n),
		high: new Float64Array(n),
		low: new Float64Array(n),
		close: new Float64Array(n),
		volume: new Float64Array(n)
	};
	let price = 50;
	for (let i = 0; i < n; i++) {
		const open = price;
		price *= 1 + (rand() - 0.5) * 0.03;
		c.time[i] = 1_700_000_000 + i * 900;
		c.open[i] = open;
		c.close[i] = price;
		c.high[i] = Math.max(open, price) * 1.002;
		c.low[i] = Math.min(open, price) * 0.998;
		c.volume[i] = 10 + rand() * 90;
	}
	return c;
}

describe('field keys', () => {
	it('round-trip for every indicator output in the catalog', () => {
		for (const entry of defaultSeriesCatalog()) {
			const parsed = parseFieldKey(entry.key);
			expect(parsed, entry.key).not.toBeNull();
			expect(makeFieldKey(parsed!.definition.id, parsed!.params, parsed!.output)).toBe(entry.key);
		}
	});

	it('rejects malformed, unknown or non-canonical keys', () => {
		expect(parseFieldKey('rsi(period=14)')).toBeNull();
		expect(parseFieldKey('nope(period=14).value')).toBeNull();
		expect(parseFieldKey('rsi(period=14).nothing')).toBeNull();
		expect(parseFieldKey('rsi(period=99999).value')).toBeNull(); // out of range: would silently clamp
		expect(isKnownField('close')).toBe(true);
		expect(isKnownField('rsi(period=99999).value')).toBe(false);
	});

	it('labels fields for people', () => {
		expect(fieldLabel('close')).toBe('Close');
		expect(fieldLabel(makeFieldKey('rsi', { period: 21 }, 'value'))).toMatch(/RSI\(21\)/);
		expect(fieldLabel('garbage')).toBe('garbage');
	});

	it('offers every raw column and indicator output as a selectable field', () => {
		const options = fieldOptions();
		expect(options.length).toBe(5 + defaultSeriesCatalog().length);
		expect(new Set(options.map((o) => o.key)).size).toBe(options.length);
		expect(INDICATORS.length).toBeGreaterThanOrEqual(100);
	});
});

describe('BarSource', () => {
	it('serves raw columns and memoises indicator series by parameters', () => {
		const source = new BarSource(columns());
		expect(source.numeric('close')).toBe(source.columns.close);
		const key = makeFieldKey('sma', { period: 5 }, 'value');
		const a = source.numeric(key);
		expect(a).not.toBeNull();
		expect(source.numeric(key)).toBe(a);
		expect(source.cachedIndicators).toBe(1);
		source.numeric(makeFieldKey('sma', { period: 6 }, 'value'));
		expect(source.cachedIndicators).toBe(2);
		expect(source.numeric('unknown')).toBeNull();
		expect(source.text()).toBeNull();
	});
});

describe('generated presets', () => {
	const presets = generatePresets();

	it('provides hundreds of presets with unique ids', () => {
		expect(presets.length).toBeGreaterThanOrEqual(500);
		expect(new Set(presets.map((p) => p.id)).size).toBe(presets.length);
	});

	it('only reference fields the source can resolve, and evaluate without issues', () => {
		const source = new BarSource(columns());
		const evaluator = createEvaluator(source, 8);
		for (const preset of presets) {
			const conditions = preset.build();
			for (const c of conditions) {
				expect(isKnownField(c.field), `${preset.id}: ${c.field}`).toBe(true);
				if (c.rhs) expect(isKnownField(c.rhs), `${preset.id}: ${c.rhs}`).toBe(true);
			}
			const result = evaluator.evaluate(newGroup('and', conditions));
			expect(result.issues, preset.id).toEqual([]);
		}
	});

	it('flags full-sample percentile presets as lookahead', () => {
		const flagged = presets.filter((p) =>
			p.build().some((c) => c.op === 'top_pct' || c.op === 'bottom_pct')
		);
		expect(flagged.length).toBeGreaterThan(0);
		expect(flagged.every((p) => p.lookahead)).toBe(true);
	});

	it('are searchable by full indicator name', () => {
		expect(presets.some((p) => p.haystack.includes('simple moving average'))).toBe(true);
	});
});

describe('explorer catalog', () => {
	const catalog = createExplorerCatalog();
	it('exposes ordered numeric fields with editable parameters', () => {
		expect(catalog.ordered).toBe(true);
		expect(catalog.kindOf('close')).toBe('numeric');
		expect(catalog.kindOf('nope')).toBeNull();
		const rsi = makeFieldKey('rsi', {}, 'value');
		const editing = catalog.params!(rsi)!;
		expect(editing.values.period).toBe(14);
		expect(editing.withParams({ period: 30 })).toBe(makeFieldKey('rsi', { period: 30 }, 'value'));
		expect(catalog.params!('close')).toBeNull();
	});
});
