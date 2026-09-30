import { describe, expect, it } from 'vitest';
import { createEvaluator, evaluateFilter } from './engine';
import {
	describeNode,
	newCondition,
	newGroup,
	normalizeTree,
	usesLookahead,
	countActive
} from './tree';
import { getOperator, operatorsFor, OPERATORS } from './operators';
import type { ColumnSource } from './types';

const NaNv = NaN;

function source(
	numeric: Record<string, number[]>,
	text: Record<string, string[]> = {},
	ordered = true
): ColumnSource {
	const columns = new Map(Object.entries(numeric).map(([k, v]) => [k, Float64Array.from(v)]));
	const length = [...columns.values()][0]?.length ?? Object.values(text)[0]?.length ?? 0;
	return {
		length,
		ordered,
		numeric: (f) => columns.get(f) ?? null,
		text: (f) => text[f] ?? null
	};
}

const run = (src: ColumnSource, ...conds: Parameters<typeof newCondition>[0][]) =>
	evaluateFilter(
		src,
		newGroup(
			'and',
			conds.map((c) => newCondition(c))
		)
	);

const bits = (mask: Uint8Array | null) => (mask ? Array.from(mask) : null);

describe('comparison operators', () => {
	const src = source({ x: [1, 2, 3, NaNv, 5], y: [3, 2, 1, 4, 5] });

	it.each([
		['gt', 2, [0, 0, 1, 0, 1]],
		['gte', 2, [0, 1, 1, 0, 1]],
		['lt', 3, [1, 1, 0, 0, 0]],
		['lte', 3, [1, 1, 1, 0, 0]],
		['eq', 2, [0, 1, 0, 0, 0]],
		['neq', 2, [1, 0, 1, 0, 1]]
	] as const)('%s against a constant never matches missing rows', (op, value, expected) => {
		expect(bits(run(src, { field: 'x', op, value }).mask)).toEqual(expected);
	});

	it('compares against another field', () => {
		expect(bits(run(src, { field: 'x', op: 'gt', rhs: 'y' }).mask)).toEqual([0, 0, 1, 0, 0]);
	});

	it('supports between / outside with unordered bounds', () => {
		expect(bits(run(src, { field: 'x', op: 'between', value: 3, value2: 1 }).mask)).toEqual([
			1, 1, 1, 0, 0
		]);
		expect(bits(run(src, { field: 'x', op: 'outside', value: 1, value2: 3 }).mask)).toEqual([
			0, 0, 0, 0, 1
		]);
	});

	it('reports validity', () => {
		expect(bits(run(src, { field: 'x', op: 'is_valid' }).mask)).toEqual([1, 1, 1, 0, 1]);
		expect(bits(run(src, { field: 'x', op: 'is_missing' }).mask)).toEqual([0, 0, 0, 1, 0]);
	});
});

describe('series operators', () => {
	it('detects crosses against a constant and another field', () => {
		const src = source({ a: [1, 3, 5, 4, 1], b: [2, 2, 2, 2, 2] });
		expect(bits(run(src, { field: 'a', op: 'crosses_above', value: 2 }).mask)).toEqual([
			0, 1, 0, 0, 0
		]);
		expect(bits(run(src, { field: 'a', op: 'crosses_below', rhs: 'b' }).mask)).toEqual([
			0, 0, 0, 0, 1
		]);
	});

	it('does not register a cross out of a missing warm-up value', () => {
		const src = source({ a: [NaNv, 5, 6] });
		expect(bits(run(src, { field: 'a', op: 'crosses_above', value: 2 }).mask)).toEqual([0, 0, 0]);
	});

	it('requires N consecutive rises or falls', () => {
		const src = source({ a: [1, 2, 3, 3, 2, 1, NaNv, 2, 3] });
		expect(bits(run(src, { field: 'a', op: 'rising', value: 2 }).mask)).toEqual([
			0, 0, 1, 0, 0, 0, 0, 0, 0
		]);
		expect(bits(run(src, { field: 'a', op: 'falling', value: 2 }).mask)).toEqual([
			0, 0, 0, 0, 0, 1, 0, 0, 0
		]);
	});

	it('finds strict N-bar highs and lows, resetting across missing values', () => {
		const src = source({ a: [1, 2, 3, 2, 4, 0, NaNv, 1, 2, 3, 0] });
		expect(bits(run(src, { field: 'a', op: 'new_high', value: 2 }).mask)).toEqual([
			0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0
		]);
		expect(bits(run(src, { field: 'a', op: 'new_low', value: 3 }).mask)).toEqual([
			0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1
		]);
	});

	it('matches a brute-force N-bar high on random data', () => {
		let seed = 7;
		const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
		const values = Array.from({ length: 500 }, () => Math.round(rand() * 20));
		const bars = 12;
		const expected = values.map((v, i) =>
			i >= bars && v > Math.max(...values.slice(i - bars, i)) ? 1 : 0
		);
		expect(
			bits(run(source({ a: values }), { field: 'a', op: 'new_high', value: bars }).mask)
		).toEqual(expected);
	});

	it('rejects series operators on unordered sources', () => {
		const result = run(source({ a: [1, 2] }, {}, false), { field: 'a', op: 'rising', value: 1 });
		expect(result.issues).toHaveLength(1);
		expect(result.matched).toBe(0);
	});
});

describe('distribution operators', () => {
	it('selects the top and bottom percent of the sample', () => {
		const src = source({ a: Array.from({ length: 100 }, (_, i) => i + 1) });
		expect(run(src, { field: 'a', op: 'top_pct', value: 10 }).matched).toBe(10);
		expect(run(src, { field: 'a', op: 'bottom_pct', value: 5 }).matched).toBe(5);
	});

	it('flags them as full-sample (lookahead) operators', () => {
		expect(getOperator('top_pct').lookahead).toBe(true);
		expect(
			usesLookahead(newGroup('and', [newCondition({ field: 'a', op: 'top_pct', value: 5 })]))
		).toBe(true);
		expect(usesLookahead(newGroup('and', [newCondition({ field: 'a', op: 'gt' })]))).toBe(false);
	});
});

describe('text operators', () => {
	const src = source({}, { name: ['SMA 5/20', 'RSI 30/50', 'sma 10/50'] });
	it('matches case-insensitively', () => {
		expect(bits(run(src, { field: 'name', op: 'contains', text: 'sma' }).mask)).toEqual([1, 0, 1]);
		expect(bits(run(src, { field: 'name', op: 'starts_with', text: 'rsi' }).mask)).toEqual([
			0, 1, 0
		]);
		expect(bits(run(src, { field: 'name', op: 'in', text: 'rsi 30/50, foo' }).mask)).toEqual([
			0, 1, 0
		]);
		expect(bits(run(src, { field: 'name', op: 'not_in', text: 'rsi 30/50' }).mask)).toEqual([
			1, 0, 1
		]);
	});

	it('flags a text operator on a numeric field', () => {
		const result = run(source({ a: [1] }), { field: 'a', op: 'contains', text: 'x' });
		expect(result.issues[0].message).toMatch(/not a text field/);
	});
});

describe('compound trees', () => {
	const src = source({ a: [1, 2, 3, 4], b: [4, 3, 2, 1] });
	const gt2 = newCondition({ field: 'a', op: 'gt', value: 2 });
	const bGt2 = newCondition({ field: 'b', op: 'gt', value: 2 });

	it('combines AND and OR groups', () => {
		expect(bits(evaluateFilter(src, newGroup('and', [gt2, bGt2])).mask)).toEqual([0, 0, 0, 0]);
		expect(bits(evaluateFilter(src, newGroup('or', [gt2, bGt2])).mask)).toEqual([1, 1, 1, 1]);
	});

	it('supports nesting and negation without mutating cached masks', () => {
		const evaluator = createEvaluator(src);
		const tree = newGroup('and', [newGroup('or', [gt2, bGt2])]);
		const inner = tree.children[0];
		if (inner.type === 'group') inner.negate = true;
		expect(bits(evaluator.evaluate(tree).mask)).toEqual([0, 0, 0, 0]);
		// The leaf masks were reused above; a second pass must give identical results.
		expect(bits(evaluator.evaluate(tree).mask)).toEqual([0, 0, 0, 0]);
		expect(bits(evaluator.evaluate(newGroup('and', [gt2])).mask)).toEqual([0, 0, 1, 1]);
	});

	it('ignores disabled and incomplete conditions', () => {
		const disabled = newCondition({ field: 'a', op: 'gt', value: 100, enabled: false });
		const incomplete = newCondition({ field: '' });
		const result = evaluateFilter(src, newGroup('and', [disabled, incomplete]));
		expect(result.mask).toBeNull();
		expect(result.matched).toBe(4);
		expect(result.issues).toEqual([]);
	});

	it('makes unknown fields match nothing and reports them', () => {
		const result = evaluateFilter(
			src,
			newGroup('and', [newCondition({ field: 'nope', op: 'gt' })])
		);
		expect(result.matched).toBe(0);
		expect(result.issues).toHaveLength(1);
	});

	it('reuses cached leaf masks', () => {
		let reads = 0;
		const counting: ColumnSource = {
			...src,
			numeric: (f) => {
				reads++;
				return src.numeric(f);
			}
		};
		const evaluator = createEvaluator(counting);
		const tree = newGroup('and', [gt2]);
		evaluator.evaluate(tree);
		evaluator.evaluate(tree);
		expect(reads).toBe(1);
		evaluator.clear();
		evaluator.evaluate(tree);
		expect(reads).toBe(2);
	});

	it('describes count and percent operators in plain grammar', () => {
		const tree = newGroup('and', [
			newCondition({ field: 'a', op: 'new_high', value: 20 }),
			newCondition({ field: 'a', op: 'top_pct', value: 5 })
		]);
		expect(describeNode(tree)).toBe('(a makes a new 20-bar high) AND (a is in the top 5%)');
	});

	it('counts only enabled, complete conditions and describes them', () => {
		const tree = newGroup('and', [
			gt2,
			newCondition({ field: '' }),
			newCondition({ field: 'b', op: 'between', value: 1, value2: 3 })
		]);
		expect(countActive(tree)).toBe(2);
		expect(describeNode(tree, (f) => f.toUpperCase())).toBe(
			'(A is above 2) AND (B is between 1 and 3)'
		);
	});
});

describe('normalizeTree', () => {
	it('drops malformed nodes and unknown operators from untrusted JSON', () => {
		const { tree, dropped } = normalizeTree({
			type: 'group',
			mode: 'or',
			children: [
				{ type: 'condition', field: 'a', op: 'gt', value: 1 },
				{ type: 'condition', field: 'a', op: 'drop_table' },
				'junk'
			]
		});
		expect(tree.mode).toBe('or');
		expect(tree.children).toHaveLength(1);
		expect(dropped).toBe(2);
		expect(normalizeTree(null).tree.children).toEqual([]);
	});
});

describe('operator registry', () => {
	it('exposes every operator once and filters by column kind', () => {
		expect(new Set(OPERATORS.map((o) => o.id)).size).toBe(OPERATORS.length);
		expect(operatorsFor('text', true).every((o) => o.family === 'text')).toBe(true);
		expect(operatorsFor('numeric', false).some((o) => o.ordered)).toBe(false);
	});
});
