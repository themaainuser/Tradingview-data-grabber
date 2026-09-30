import { expect, it } from 'vitest';
import { groupBy, uniqueBy } from './group';

it('groups preserving first-seen order', () => {
	expect(groupBy(['a1', 'b1', 'a2'], (s) => s[0])).toEqual([
		['a', ['a1', 'a2']],
		['b', ['b1']]
	]);
	expect(groupBy([], () => 'x')).toEqual([]);
});

it('keeps the first of each key', () => {
	expect(
		uniqueBy(
			[
				{ k: 'a', v: 1 },
				{ k: 'a', v: 2 },
				{ k: 'b', v: 3 }
			],
			(o) => o.k
		).map((o) => o.v)
	).toEqual([1, 3]);
});
