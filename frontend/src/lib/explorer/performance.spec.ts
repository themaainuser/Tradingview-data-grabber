import { describe, expect, it } from 'vitest';
import { eventStudy } from '$lib/analysis/event-study';
import { createEvaluator } from '$lib/filters/engine';
import { newCondition, newGroup } from '$lib/filters/tree';
import { BarSource } from './bar-source';
import { makeFieldKey } from './fields';

/** Seeded random walk at the scale of a long intraday capture (test data only). */
function columns(n: number) {
	let seed = 11;
	const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
	const c = {
		time: new Float64Array(n),
		open: new Float64Array(n),
		high: new Float64Array(n),
		low: new Float64Array(n),
		close: new Float64Array(n),
		volume: new Float64Array(n)
	};
	let price = 100;
	for (let i = 0; i < n; i++) {
		const open = price;
		price *= 1 + (rand() - 0.5) * 0.004;
		c.time[i] = 1_600_000_000 + i * 60;
		c.open[i] = open;
		c.close[i] = price;
		c.high[i] = Math.max(open, price) * 1.0005;
		c.low[i] = Math.min(open, price) * 0.9995;
		c.volume[i] = 10 + rand() * 90;
	}
	return c;
}

const time = <T>(fn: () => T): [T, number] => {
	const start = performance.now();
	const result = fn();
	return [result, performance.now() - start];
};

describe('interactive budgets at 500,000 bars', () => {
	const n = 500_000;
	const source = new BarSource(columns(n));
	const evaluator = createEvaluator(source);
	const rsi = makeFieldKey('rsi', { period: 14 }, 'value');
	const sma = makeFieldKey('sma', { period: 50 }, 'value');
	const conditions = [
		newCondition({ field: rsi, op: 'lt', value: 35 }),
		newCondition({ field: 'close', op: 'gt', rhs: sma }),
		newCondition({ field: 'volume', op: 'new_high', value: 20 })
	];
	const tree = newGroup('and', conditions);

	it('evaluates a three-indicator compound filter cold within budget', () => {
		const [result, ms] = time(() => evaluator.evaluate(tree));
		console.info(
			`cold compound filter over ${n} bars: ${ms.toFixed(0)} ms (${result.matched} matches)`
		);
		expect(result.issues).toEqual([]);
		expect(ms).toBeLessThan(3000);
	});

	it('re-evaluates after editing one threshold without recomputing indicators', () => {
		evaluator.evaluate(tree);
		conditions[0].value = 40;
		const [result, ms] = time(() => evaluator.evaluate(tree));
		console.info(`threshold edit re-evaluation: ${ms.toFixed(1)} ms (${result.matched} matches)`);
		expect(ms).toBeLessThan(250);
	});

	it('serves an unchanged filter from the leaf cache', () => {
		evaluator.evaluate(tree);
		const [, ms] = time(() => evaluator.evaluate(tree));
		console.info(`cached re-evaluation: ${ms.toFixed(1)} ms`);
		expect(ms).toBeLessThan(120);
	});

	it('computes the forward-return study within budget', () => {
		const mask = evaluator.evaluate(tree).mask!;
		const [study, ms] = time(() => eventStudy(source.columns.close, mask, [1, 5, 10, 20, 50]));
		console.info(`event study (5 horizons): ${ms.toFixed(0)} ms over ${study.events} events`);
		expect(ms).toBeLessThan(500);
	});
});
