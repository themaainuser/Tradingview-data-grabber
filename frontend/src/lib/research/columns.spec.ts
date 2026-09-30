import { describe, expect, it } from 'vitest';
import type { PerformanceMetrics, ResearchReport, ResearchResult } from '$lib/api/contracts';
import { evaluateFilter } from '$lib/filters/engine';
import { newCondition, newGroup } from '$lib/filters/tree';
import { buildColumns, createResearchTable, sortRows } from './columns';

const metrics = (o: Partial<PerformanceMetrics> = {}): PerformanceMetrics => ({
	bars: 100,
	total_return_pct: 0,
	cagr_pct: 0,
	annualized_volatility_pct: 10,
	sharpe: 0,
	sortino: 0,
	max_drawdown_pct: -5,
	calmar: 0,
	trades: 4,
	win_rate_pct: 50,
	exposure_pct: 40,
	...o
});

const result = (
	id: string,
	family: string,
	params: Record<string, number>,
	forward: Partial<PerformanceMetrics>,
	folds: Partial<PerformanceMetrics>[] = []
): ResearchResult => ({
	id,
	symbol: 'BTC',
	source: 'btc.csv',
	family,
	name: id,
	parameters: params,
	metrics: {
		full_sample: metrics({ total_return_pct: 12, sharpe: 1 }),
		in_sample: metrics({ sharpe: 2 }),
		forward: metrics(forward)
	},
	forward_folds: folds.map((f, i) => ({ start: `${i}`, end: `${i}`, metrics: metrics(f) })),
	equity_curve: [
		['a', 1],
		['b', 1.12]
	],
	benchmark_curve: []
});

const report = (results: ResearchResult[]): ResearchReport => ({
	schema_version: 1,
	metadata: {
		fee_bps_per_position_change: 5,
		periods_per_year: 252,
		strategy_count_per_asset: results.length,
		forward_validation: ''
	},
	assets: [
		{
			symbol: 'BTC',
			source: 'btc.csv',
			rows: 100,
			start: 'a',
			end: 'b',
			quality: {} as never,
			benchmark: metrics({ total_return_pct: 10, sharpe: 0.5, max_drawdown_pct: -20 }),
			benchmark_curve: []
		}
	],
	results,
	model_notes: [],
	disclosures: []
});

const data = report([
	result('sma-5-20', 'SMA crossover', { fast: 5, slow: 20 }, { sharpe: 1.5, total_return_pct: 4 }, [
		{ total_return_pct: 2, sharpe: 1 },
		{ total_return_pct: -1, sharpe: -0.5 }
	]),
	result('rsi-30-50', 'RSI mean reversion', { entry: 30, exit: 50 }, { sharpe: null }),
	result(
		'sma-10-50',
		'SMA crossover',
		{ fast: 10, slow: 50 },
		{ sharpe: -0.2, total_return_pct: -3 }
	)
]);

describe('research columns', () => {
	it('exposes metric, relative, fold and parameter columns', () => {
		const keys = buildColumns(data).map((c) => c.key);
		expect(keys).toContain('forward.sharpe');
		expect(keys).toContain('in_sample.max_drawdown_pct');
		expect(keys).toContain('rel.excess_return');
		expect(keys).toContain('fold.sharpe_min');
		expect(keys).toEqual(
			expect.arrayContaining(['param.fast', 'param.slow', 'param.entry', 'param.exit'])
		);
		expect(keys.length).toBeGreaterThan(50);
	});

	it('derives comparisons against the market benchmark and fold aggregates', () => {
		const { source } = createResearchTable(data);
		expect(source.numeric('rel.excess_return')![0]).toBeCloseTo(2);
		expect(source.numeric('rel.drawdown_gain')![0]).toBeCloseTo(15);
		expect(source.numeric('fold.positive')![0]).toBe(1);
		expect(source.numeric('fold.return_min')![0]).toBe(-1);
		expect(source.numeric('curve.final_equity')![0]).toBeCloseTo(1.12);
	});

	it('maps null metrics and inapplicable parameters to NaN, never zero', () => {
		const { source } = createResearchTable(data);
		expect(source.numeric('forward.sharpe')![1]).toBeNaN();
		expect(source.numeric('param.fast')![1]).toBeNaN();
		expect(source.numeric('fold.sharpe_mean')![1]).toBeNaN();
		// A genuine zero must survive (fold return of exactly 0 is not "missing").
		const zero = createResearchTable(
			report([result('z', 'SMA crossover', { fast: 1, slow: 2 }, {}, [{ total_return_pct: 0 }])])
		);
		expect(zero.source.numeric('fold.return_min')![0]).toBe(0);
	});

	it('filters through the shared engine, including compound and text conditions', () => {
		const { source } = createResearchTable(data);
		const tree = newGroup('and', [
			newCondition({ field: 'family', op: 'contains', text: 'sma' }),
			newCondition({ field: 'forward.sharpe', op: 'gt', value: 0 })
		]);
		expect(Array.from(evaluateFilter(source, tree).mask!)).toEqual([1, 0, 0]);
		const missing = newGroup('and', [newCondition({ field: 'forward.sharpe', op: 'is_missing' })]);
		expect(Array.from(evaluateFilter(source, missing).mask!)).toEqual([0, 1, 0]);
	});

	it('sorts stably with missing values last in both directions', () => {
		const table = createResearchTable(data);
		expect(Array.from(sortRows(table, null, 'forward.sharpe', 'desc'))).toEqual([0, 2, 1]);
		expect(Array.from(sortRows(table, null, 'forward.sharpe', 'asc'))).toEqual([2, 0, 1]);
		expect(Array.from(sortRows(table, Uint8Array.from([1, 0, 1]), 'name', 'asc'))).toEqual([2, 0]);
	});
});
