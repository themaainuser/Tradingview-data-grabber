import { describe, expect, it, vi } from 'vitest';
import type { ApiClient } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { Bars } from '$lib/api/validate';
import type { PerformanceMetrics, ResearchReport } from '$lib/api/contracts';
import { newCondition } from '$lib/filters/tree';
import { DatasetsStore } from './datasets.svelte';
import { ExplorerStore } from './explorer.svelte';
import { ResearchStore } from './research.svelte';
import { SavedFilters } from './saved-filters.svelte';

/** Deterministic random-walk bars; test data only, never shipped to the UI. */
function makeBars(n = 300, id = 'ds1'): Bars {
	let seed = 42;
	const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
	const columns = {
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
		price = Math.max(1, price * (1 + (rand() - 0.5) * 0.02));
		columns.time[i] = 1_700_000_000 + i * 3600;
		columns.open[i] = open;
		columns.close[i] = price;
		columns.high[i] = Math.max(open, price) * 1.001;
		columns.low[i] = Math.min(open, price) * 0.999;
		columns.volume[i] = 100 + rand() * 50;
	}
	return {
		id,
		symbol: 'TEST',
		timeframe: '60',
		columns,
		length: n,
		totalRows: n,
		droppedRows: 0,
		duplicateRows: 0,
		quality: null,
		origin: 'backend'
	};
}

const api = (overrides: Partial<ApiClient>): ApiClient =>
	({
		listDatasets: vi.fn(),
		getBars: vi.fn(),
		runResearch: vi.fn(),
		...overrides
	}) as unknown as ApiClient;

const deferred = <T>() => {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
	return { promise, resolve, reject };
};

describe('DatasetsStore', () => {
	const summary = {
		id: 'a',
		symbol: 'X',
		timeframe: '5',
		path: 'X/5.csv',
		rows: 3,
		size_bytes: 1,
		modified: '',
		start: 1,
		end: 2,
		valid: true,
		error: null
	};

	it('starts empty and stays empty when the backend has no datasets', async () => {
		const store = new DatasetsStore(api({ listDatasets: vi.fn(async () => []) }));
		expect(store.items).toEqual([]);
		expect(store.isEmpty).toBe(false); // not "empty" until a load has actually completed
		await store.load();
		expect(store.status).toBe('ready');
		expect(store.isEmpty).toBe(true);
	});

	it('keeps invalid files listed but not usable', async () => {
		const store = new DatasetsStore(
			api({
				listDatasets: vi.fn(async () => [
					summary,
					{ ...summary, id: 'b', valid: false, error: 'bad' }
				])
			})
		);
		await store.load();
		expect(store.items).toHaveLength(2);
		expect(store.usable.map((d) => d.id)).toEqual(['a']);
	});

	it('surfaces load failures and recovers on retry', async () => {
		const listDatasets = vi
			.fn()
			.mockRejectedValueOnce(new ApiError('network', 'down'))
			.mockResolvedValueOnce([summary]);
		const store = new DatasetsStore(api({ listDatasets }));
		await store.load();
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('down');
		await store.load();
		expect(store.status).toBe('ready');
		expect(store.error).toBeNull();
	});

	it('ignores a superseded load', async () => {
		const first = deferred<never[]>();
		const listDatasets = vi
			.fn()
			.mockReturnValueOnce(first.promise)
			.mockResolvedValueOnce([summary]);
		const store = new DatasetsStore(api({ listDatasets }));
		const stale = store.load();
		await store.load();
		first.resolve([]);
		await stale;
		expect(store.items).toEqual([summary]);
	});

	it('imports a CSV locally and reports rejected files', async () => {
		const store = new DatasetsStore(api({}));
		const good = new File(['time,open,high,low,close,volume\n1700000000,1,2,1,2,5\n'], 'btc.csv');
		const bars = await store.importFile(good);
		expect(bars?.origin).toBe('local');
		expect(store.local).toHaveLength(1);
		expect(store.findLocal(bars!.id)).toBe(bars);
		expect(await store.importFile(new File(['nope'], 'bad.csv'))).toBeNull();
		expect(store.importError).toMatch(/Missing required column/);
		store.dismissImportError();
		expect(store.importError).toBeNull();
		store.removeLocal(bars!.id);
		expect(store.local).toHaveLength(0);
	});
});

describe('ExplorerStore', () => {
	it('loads bars and ignores a superseded request', async () => {
		const slow = deferred<Bars>();
		const getBars = vi
			.fn()
			.mockReturnValueOnce(slow.promise)
			.mockResolvedValueOnce(makeBars(50, 'fast'));
		const store = new ExplorerStore(api({ getBars }));
		const first = store.openBackend('slow');
		await store.openBackend('fast');
		slow.resolve(makeBars(50, 'slow'));
		await first;
		expect(store.bars?.id).toBe('fast');
		expect(store.status).toBe('ready');
	});

	it('exposes a load failure instead of stale bars', async () => {
		const store = new ExplorerStore(
			api({
				getBars: vi.fn(async () => {
					throw new ApiError('http', 'Unknown dataset id', 404);
				})
			})
		);
		await store.openBackend('missing');
		expect(store.status).toBe('error');
		expect(store.bars).toBeNull();
		expect(store.error?.status).toBe(404);
	});

	it('builds chart overlays and panes from indicator instances and memoises compute', () => {
		const store = new ExplorerStore(api({}));
		store.openLocal(makeBars());
		expect(store.chart).toEqual({ overlays: [], panes: [] });
		const sma = store.addIndicator('sma', { period: 10 })!;
		store.addIndicator('rsi');
		expect(store.chart.overlays).toHaveLength(1);
		expect(store.chart.overlays[0].label).toBe('SMA(10)');
		expect(store.chart.panes).toHaveLength(1);
		expect(store.chart.overlays[0].values).toHaveLength(300);
		expect(store.chart.overlays[0].values[0]).toBeNaN(); // warm-up is missing, never zero
		const before = store.source!.cachedIndicators;
		store.updateIndicator(sma, { period: 10 });
		expect(store.chart.overlays).toHaveLength(1);
		expect(store.source!.cachedIndicators).toBe(before);
		store.toggleIndicator(sma);
		expect(store.chart.overlays).toHaveLength(0);
		store.removeIndicator(sma);
		expect(store.indicators).toHaveLength(1);
		expect(store.addIndicator('does_not_exist')).toBeNull();
	});

	it('evaluates compound filters, matches and forward statistics as the tree is edited', () => {
		const store = new ExplorerStore(api({}));
		store.openLocal(makeBars());
		expect(store.evaluation?.mask).toBeNull();
		expect(store.study?.events ?? 0).toBe(0);
		const editor = store.filterEditor;
		editor.add(store.filter.id, newCondition({ field: 'close', op: 'gt', value: 100 }));
		const id = store.filter.children[0].id;
		const total = store.evaluation!.matched;
		expect(total).toBeGreaterThan(0);
		expect(total).toBeLessThan(300);
		expect(store.matches).toHaveLength(total);
		expect(store.study!.events).toBe(total);
		editor.patch(id, { value: 1e9 });
		expect(store.evaluation!.matched).toBe(0);
		expect(store.study!.horizons[0].n).toBe(0);
		editor.patch(id, { field: 'sma(period=20).value', op: 'crosses_above', rhs: 'close' });
		expect(store.evaluation!.issues).toEqual([]);
		editor.patch(id, { field: 'bogus' });
		expect(store.evaluation!.issues).toHaveLength(1);
		expect(store.referencedFields).toContain('bogus');
		editor.remove(id);
		expect(store.evaluation!.mask).toBeNull();
	});

	it('reduces matches to run onsets on request', () => {
		const store = new ExplorerStore(api({}));
		store.openLocal(makeBars());
		store.filterEditor.add(store.filter.id, newCondition({ field: 'close', op: 'gt', value: 100 }));
		const all = store.matches.length;
		store.onsetOnly = true;
		expect(store.matches.length).toBeLessThan(all);
		expect(store.matches.length).toBeGreaterThan(0);
	});
});

const metrics = (o: Partial<PerformanceMetrics> = {}): PerformanceMetrics => ({
	bars: 100,
	total_return_pct: 1,
	cagr_pct: 1,
	annualized_volatility_pct: 1,
	sharpe: 1,
	sortino: 1,
	max_drawdown_pct: -1,
	calmar: 1,
	trades: 3,
	win_rate_pct: 50,
	exposure_pct: 50,
	...o
});

const report = (sharpes: (number | null)[]): ResearchReport => ({
	schema_version: 1,
	metadata: {
		fee_bps_per_position_change: 5,
		periods_per_year: 252,
		strategy_count_per_asset: sharpes.length,
		forward_validation: ''
	},
	assets: [
		{
			symbol: 'X',
			source: 'x.csv',
			rows: 1,
			start: '',
			end: '',
			quality: {} as never,
			benchmark: metrics(),
			benchmark_curve: []
		}
	],
	results: sharpes.map((sharpe, i) => ({
		id: `r${i}`,
		symbol: 'X',
		source: 'x.csv',
		family: 'SMA crossover',
		name: `S${i}`,
		parameters: { fast: i + 1 },
		metrics: { full_sample: metrics(), in_sample: metrics(), forward: metrics({ sharpe }) },
		forward_folds: [],
		equity_curve: [],
		benchmark_curve: []
	})),
	model_notes: [],
	disclosures: []
});

describe('ResearchStore', () => {
	it('holds nothing before a run and refuses to run with invalid input', async () => {
		const runResearch = vi.fn();
		const store = new ResearchStore(api({ runResearch }));
		expect(store.report).toBeNull();
		expect(store.table).toBeNull();
		expect(store.order).toHaveLength(0);
		expect(store.canRun).toBe(false);
		await store.run();
		expect(runResearch).not.toHaveBeenCalled();
		store.toggleDataset('a');
		expect(store.canRun).toBe(true);
		store.feeBps = -1;
		expect(store.validation.feeBps).not.toBeNull();
		expect(store.canRun).toBe(false);
		store.feeBps = 5;
		store.periodsPerYear = 0;
		expect(store.canRun).toBe(false);
	});

	it('sends the form values and exposes the sorted, filtered report', async () => {
		const runResearch = vi.fn(async () => report([0.5, null, 2, -1]));
		const store = new ResearchStore(api({ runResearch }));
		store.toggleDataset('a');
		store.feeBps = 7;
		store.periodsPerYear = 365;
		await store.run();
		expect(runResearch).toHaveBeenCalledWith(
			{ dataset_ids: ['a'], fee_bps: 7, periods_per_year: 365 },
			expect.anything()
		);
		expect(store.status).toBe('ready');
		expect(Array.from(store.order)).toEqual([2, 0, 3, 1]); // forward Sharpe desc, missing last
		store.setSort('forward.sharpe');
		expect(store.sortDir).toBe('asc');
		expect(Array.from(store.order)).toEqual([3, 0, 2, 1]);
		store.filterEditor.add(
			store.filter.id,
			newCondition({ field: 'forward.sharpe', op: 'gt', value: 0 })
		);
		expect(Array.from(store.order)).toEqual([0, 2]);
		expect(store.evaluation!.matched).toBe(2);
	});

	it('keeps the previous report visible when a later run fails', async () => {
		const runResearch = vi
			.fn()
			.mockResolvedValueOnce(report([1]))
			.mockRejectedValueOnce(new ApiError('http', 'unknown dataset id: a', 422));
		const store = new ResearchStore(api({ runResearch }));
		store.toggleDataset('a');
		await store.run();
		await store.run();
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('unknown dataset id: a');
		expect(store.report?.results).toHaveLength(1);
	});

	it('cancels an in-flight run without reporting an error', async () => {
		const pending = deferred<ResearchReport>();
		const runResearch = vi.fn((_body, opts?: { signal?: AbortSignal }) => {
			opts?.signal?.addEventListener('abort', () =>
				pending.reject(new ApiError('aborted', 'cancelled'))
			);
			return pending.promise;
		});
		const store = new ResearchStore(api({ runResearch: runResearch as never }));
		store.toggleDataset('a');
		const running = store.run();
		expect(store.status).toBe('loading');
		store.cancel();
		await running;
		expect(store.status).toBe('idle');
		expect(store.error).toBeNull();
	});

	it('limits the equity comparison to six strategies', () => {
		const store = new ResearchStore(api({}));
		for (let i = 0; i < 8; i++) store.toggleCompare(`r${i}`);
		expect(store.compareIds).toHaveLength(6);
		store.toggleCompare('r0');
		expect(store.compareIds).toHaveLength(5);
	});
});

describe('SavedFilters', () => {
	const memory = (initial: Record<string, string> = {}): Storage => {
		const data = new Map(Object.entries(initial));
		return {
			getItem: (k: string) => data.get(k) ?? null,
			setItem: (k: string, v: string) => void data.set(k, v),
			removeItem: (k: string) => void data.delete(k),
			clear: () => data.clear(),
			key: () => null,
			get length() {
				return data.size;
			}
		} as Storage;
	};

	it('starts empty, saves, replaces by name and persists across instances', () => {
		const storage = memory();
		const saved = new SavedFilters('t', storage);
		expect(saved.items).toEqual([]);
		const store = new ExplorerStore(api({}));
		store.filterEditor.add(store.filter.id, newCondition({ field: 'close', op: 'gt', value: 1 }));
		expect(saved.save('  ', store.filter)).toBeNull();
		saved.save('mine', store.filter);
		saved.save('mine', store.filter);
		expect(saved.items).toHaveLength(1);
		const reloaded = new SavedFilters('t', storage);
		expect(reloaded.items[0].name).toBe('mine');
		expect(reloaded.items[0].tree.children).toHaveLength(1);
		reloaded.remove(reloaded.items[0].id);
		expect(new SavedFilters('t', storage).items).toEqual([]);
	});

	it('survives corrupt storage and write failures', () => {
		expect(new SavedFilters('t', memory({ 'qr:filters:t': '{not json' })).items).toEqual([]);
		expect(
			new SavedFilters(
				't',
				memory({
					'qr:filters:t': JSON.stringify([
						{
							name: 'x',
							tree: {
								type: 'group',
								children: [{ type: 'condition', field: 'a', op: 'drop table' }]
							}
						}
					])
				})
			).items[0].tree.children
		).toEqual([]);
		const failing = memory();
		failing.setItem = () => {
			throw new DOMException('full', 'QuotaExceededError');
		};
		const saved = new SavedFilters('t', failing);
		saved.save('a', new ExplorerStore(api({})).filter);
		expect(saved.items).toHaveLength(1);
		expect(saved.persistError).toMatch(/Could not persist/);
	});
});
