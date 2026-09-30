import { describe, expect, it, vi } from 'vitest';
import type { ApiClient } from '$lib/api/client';
import type {
	HoldoutInfo,
	HoldoutResult,
	VerdictFreeze,
	VerdictReport,
	VerdictRule,
	VerdictState
} from '$lib/api/contracts';
import { ApiError } from '$lib/api/errors';
import { MAX_FINALISTS, VerdictStore } from './verdict.svelte';

const deferred = <T>() => {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
	return { promise, resolve, reject };
};

const holdout = (overrides: Partial<HoldoutInfo> = {}): HoldoutInfo => ({
	fraction: 0.2,
	start: 1_000,
	end: 2_000,
	bars: 200,
	sealed_at: 2_100,
	status: 'unread',
	read_at: null,
	...overrides
});

const rule = (id: string, candidate = false): VerdictRule => ({
	id,
	family: 'SMA crossover',
	name: id.toUpperCase(),
	parameters: { fast: 5, slow: 20 },
	status: candidate ? 'PASSED_GATE' : 'INSUFFICIENT_TRADES',
	trades: candidate ? 50 : 4,
	closed_trades: candidate ? 49 : 4,
	exposure_pct: 40,
	error: null,
	evidence: candidate
		? {
				sharpe: 1,
				sharpe_se: 2,
				mean_trade_return_pct: 0.3,
				adjusted_p: 0.01,
				dsr: 0.97,
				dsr_sensitivity: { low_n: { n: 2, dsr: 0.98 }, high_n: { n: 6, dsr: 0.96 } },
				break_even: { round_trip_bps: 60, base_round_trip_bps: 22, multiple: 2.7 },
				stress: [],
				checks: { bootstrap: true, dsr: true, stress: true },
				candidate: true
			}
		: null
});

function report(label: VerdictReport['verdict']['label'], rules: VerdictRule[]): VerdictReport {
	return {
		run_id: 'run-1',
		created_at: 3_000,
		dataset: { id: 'a', symbol: 'BTC', timeframe: '60', path: 'BTC/60.csv' },
		verdict: { label, headline: 'headline', reasons: [] },
		settings: {
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: 8760,
			periods_per_year_inferred: true,
			alpha: 0.05,
			dsr_threshold: 0.95,
			stress_multipliers: [1, 1.5, 2],
			bootstrap: { replicates: 2000, mean_block_length: 9, seed: 1 }
		},
		data: {
			bars_total: 1000,
			research_bars: 800,
			research_start: 10,
			research_end: 1_000,
			forward_bars: 0,
			holdout: { ...holdout(), created_now: true }
		},
		ledger: { trials_dataset: 16, trials_total: 16, runs_dataset: 1, intact: true },
		rules,
		statistics: null,
		uncertainty: {
			research_bars: 800,
			sharpe_se_annualised_iid: 3,
			holdout_bars: 200,
			holdout_sharpe_se_annualised_iid: 6,
			note: 'n'
		},
		integrity: {
			fill_model: 'next_open',
			signal_shift_verified: true,
			lookahead_probe: { passed: true, rules_checked: 16, truncation_bar: 600 },
			close_to_open_gap_bps: { mean_abs: 0, p99_abs: 0, max_abs: 0 },
			research_fingerprint: 'abc'
		},
		notes: []
	};
}

const freeze: VerdictFreeze = {
	id: 'f1',
	run_id: 'run-1',
	rule_ids: ['sma-5-20'],
	rules: [
		{ id: 'sma-5-20', name: 'SMA 5/20', family: 'SMA crossover', parameters: { fast: 5, slow: 20 } }
	],
	frozen_at: 4_000,
	forward_start: 2_000,
	hash: 'h'
};

function verdictState(overrides: Partial<VerdictState> = {}): VerdictState {
	return {
		dataset: { id: 'a', symbol: 'BTC', timeframe: '60', path: 'BTC/60.csv', rows: 1000 },
		sealed: false,
		holdout: null,
		ledger: { trials_dataset: 0, trials_total: 0, runs_dataset: 0, intact: true },
		latest: null,
		freeze: null,
		holdout_read: null,
		defaults: {
			min_trades: 30,
			holdout_fraction: 0.2,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			cost_notes: [],
			bootstrap_replicates: 2000,
			alpha: 0.05,
			dsr_threshold: 0.95,
			stress_multipliers: [1, 1.5, 2]
		},
		...overrides
	};
}

const api = (overrides: Partial<ApiClient>) => overrides as unknown as ApiClient;

/** A store with the dataset already opened. */
async function opened(state: VerdictState, overrides: Partial<ApiClient> = {}) {
	const getVerdictState = vi.fn(async () => state);
	const store = new VerdictStore(api({ getVerdictState, ...overrides }));
	await store.open('a');
	return { store, getVerdictState };
}

describe('VerdictStore: loading', () => {
	it('fills the form from the backend defaults and holds no report yet', async () => {
		const { store } = await opened(verdictState());
		expect(store.status).toBe('ready');
		expect(store.form).toMatchObject({ minTrades: 30, fee: 10, spread: 1, slippageK: 0.1 });
		expect(store.report).toBeNull();
		expect(store.sealed).toBe(false);
	});

	it('keeps the user\u2019s edits across a reload of the same dataset but resets for another', async () => {
		const { store } = await opened(verdictState());
		store.form.fee = 7;
		await store.reload();
		expect(store.form.fee).toBe(7);
		await store.open('b');
		expect(store.form.fee).toBe(10);
		expect(store.state?.latest).toBeNull();
	});

	it('reports a load failure and keeps nothing', async () => {
		const store = new VerdictStore(
			api({
				getVerdictState: vi.fn(async () =>
					Promise.reject(new ApiError('http', 'dataset not found', 404))
				)
			})
		);
		await store.open('zzz');
		expect(store.status).toBe('error');
		expect(store.error?.message).toBe('dataset not found');
		expect(store.state).toBeNull();
	});

	it('ignores a superseded open, including its abort', async () => {
		const first = deferred<VerdictState>();
		const second = verdictState({ dataset: { ...verdictState().dataset, id: 'b' } });
		const getVerdictState = vi
			.fn()
			.mockReturnValueOnce(first.promise)
			.mockResolvedValueOnce(second);
		const store = new VerdictStore(api({ getVerdictState }));
		const older = store.open('a');
		await store.open('b');
		first.reject(new DOMException('aborted', 'AbortError'));
		await older;
		expect(store.state?.dataset.id).toBe('b');
		expect(store.error).toBeNull();
	});
});

describe('VerdictStore: running', () => {
	it('does not call the backend while the form is invalid', async () => {
		const runVerdict = vi.fn();
		const sealHoldout = vi.fn();
		const { store } = await opened(verdictState(), { runVerdict, sealHoldout });
		store.form.minTrades = 0;
		expect(store.canRun).toBe(false);
		await store.run();
		expect(runVerdict).not.toHaveBeenCalled();
		expect(sealHoldout).not.toHaveBeenCalled();
	});

	it('seals the holdout with the chosen share first when the dataset is unsealed', async () => {
		const order: string[] = [];
		const sealHoldout = vi.fn(async (_id: string, fraction: number) => {
			order.push(`seal:${fraction}`);
			return holdout({ fraction });
		});
		const runVerdict = vi.fn(async () => {
			order.push('run');
			return report('INSUFFICIENT_DATA', [rule('sma-5-20')]);
		});
		const { store } = await opened(verdictState(), { sealHoldout, runVerdict });
		store.form.holdoutFraction = 0.25;
		await store.run();
		expect(order).toEqual(['seal:0.25', 'run']);
		expect(store.runStatus).toBe('ready');
	});

	it('does not seal again when the dataset is already sealed', async () => {
		const sealHoldout = vi.fn();
		const runVerdict = vi.fn(async () => report('INSUFFICIENT_DATA', [rule('sma-5-20')]));
		const { store } = await opened(verdictState({ sealed: true, holdout: holdout() }), {
			sealHoldout,
			runVerdict
		});
		await store.run();
		expect(sealHoldout).not.toHaveBeenCalled();
		expect(runVerdict).toHaveBeenCalledWith({
			dataset_id: 'a',
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: null
		});
	});

	it('shows the returned report, the new seal and the ledger count, and keeps them after the re-sync', async () => {
		const result = report('INSUFFICIENT_DATA', [rule('sma-5-20')]);
		// A stateful fake: like the real backend, it serves the run it just stored.
		let served = verdictState();
		const getVerdictState = vi.fn(async () => served);
		const runVerdict = vi.fn(async () => {
			served = {
				...served,
				sealed: true,
				holdout: holdout(),
				ledger: result.ledger,
				latest: result
			};
			return result;
		});
		const store = new VerdictStore(
			api({ getVerdictState, sealHoldout: vi.fn(async () => holdout()), runVerdict })
		);
		await store.open('a');
		await store.run();
		expect(store.report).toEqual(result);
		expect(store.sealed).toBe(true);
		expect(store.state?.holdout?.status).toBe('unread');
		expect(store.state?.ledger.trials_dataset).toBe(16);
	});

	it('ignores a second click while a run is in flight', async () => {
		const pending = deferred<VerdictReport>();
		const runVerdict = vi.fn(() => pending.promise);
		const { store } = await opened(verdictState({ sealed: true, holdout: holdout() }), {
			runVerdict
		});
		const first = store.run();
		expect(store.runStatus).toBe('loading');
		expect(store.canRun).toBe(false);
		await store.run();
		expect(runVerdict).toHaveBeenCalledTimes(1);
		pending.resolve(report('INSUFFICIENT_DATA', [rule('sma-5-20')]));
		await first;
	});

	it('reports a failed run and asks the server what actually happened', async () => {
		const getVerdictState = vi.fn(async () => verdictState({ sealed: true, holdout: holdout() }));
		const runVerdict = vi.fn(async () =>
			Promise.reject(new ApiError('http', 'ledger integrity check failed', 409))
		);
		const store = new VerdictStore(api({ getVerdictState, runVerdict }));
		await store.open('a');
		const before = getVerdictState.mock.calls.length;
		await store.run();
		expect(store.runStatus).toBe('error');
		expect(store.runError?.message).toBe('ledger integrity check failed');
		expect(getVerdictState.mock.calls.length).toBe(before + 1);
	});

	it('locks every action when the ledger chain is broken', async () => {
		const { store } = await opened(
			verdictState({
				sealed: true,
				holdout: holdout(),
				ledger: { trials_dataset: 16, trials_total: 16, runs_dataset: 1, intact: false }
			})
		);
		expect(store.locked).toBe(true);
		expect(store.canRun).toBe(false);
	});

	it('flags settings that differ from the report on screen', async () => {
		const { store } = await opened(
			verdictState({
				sealed: true,
				holdout: holdout(),
				latest: report('INSUFFICIENT_DATA', [rule('sma-5-20')])
			})
		);
		expect(store.differs).toBe(false);
		store.form.fee = 25;
		expect(store.differs).toBe(true);
	});
});

describe('VerdictStore: finalists, freeze and holdout', () => {
	const candidateState = () =>
		verdictState({
			sealed: true,
			holdout: holdout(),
			latest: report('CANDIDATE', [
				rule('sma-5-20', true),
				rule('sma-10-20', true),
				rule('sma-5-50', true),
				rule('rsi-30-50')
			])
		});

	it('only lets candidates be chosen, at most two', async () => {
		const { store } = await opened(candidateState());
		store.toggleFinalist('rsi-30-50');
		expect(store.selectedRuleIds).toEqual([]);
		store.toggleFinalist('sma-5-20');
		store.toggleFinalist('sma-10-20');
		store.toggleFinalist('sma-5-50');
		expect(store.selectedRuleIds).toEqual(['sma-5-20', 'sma-10-20']);
		expect(MAX_FINALISTS).toBe(2);
		store.toggleFinalist('sma-5-20');
		expect(store.selectedRuleIds).toEqual(['sma-10-20']);
	});

	it('cannot freeze without a candidate verdict or without a selection', async () => {
		const noCandidate = await opened(
			verdictState({
				sealed: true,
				holdout: holdout(),
				latest: report('INSUFFICIENT_DATA', [rule('sma-5-20')])
			})
		);
		noCandidate.store.selectedRuleIds = ['sma-5-20'];
		expect(noCandidate.store.canFreeze).toBe(false);
		const { store } = await opened(candidateState());
		expect(store.canFreeze).toBe(false);
		store.toggleFinalist('sma-5-20');
		expect(store.canFreeze).toBe(true);
	});

	it('freezes the selected rules against the latest run and refreshes', async () => {
		const freezeRules = vi.fn(async () => freeze);
		const { store, getVerdictState } = await opened(candidateState(), { freezeRules });
		store.toggleFinalist('sma-5-20');
		const before = getVerdictState.mock.calls.length;
		await store.freeze();
		expect(freezeRules).toHaveBeenCalledWith('a', { run_id: 'run-1', rule_ids: ['sma-5-20'] });
		expect(store.freezeStatus).toBe('ready');
		expect(getVerdictState.mock.calls.length).toBe(before + 1);
	});

	it('cannot freeze twice once a freeze exists', async () => {
		const { store } = await opened({ ...candidateState(), freeze });
		store.toggleFinalist('sma-5-20');
		expect(store.canFreeze).toBe(false);
	});

	const read: HoldoutResult = {
		freeze_id: 'f1',
		read_at: 5_000,
		start: 1_000,
		end: 2_000,
		bars: 200,
		rules: [],
		caveat: 'c',
		sharpe_se_annualised_iid: 6
	};

	it('reads the holdout only with a freeze and an unread holdout', async () => {
		const readHoldout = vi.fn(async () => read);
		const unfrozen = await opened(candidateState(), { readHoldout });
		expect(unfrozen.store.canRead).toBe(false);
		await unfrozen.store.readHoldout();
		expect(readHoldout).not.toHaveBeenCalled();

		const consumed = await opened(
			{
				...candidateState(),
				freeze,
				holdout: holdout({ status: 'read', read_at: 5_000 }),
				holdout_read: read
			},
			{ readHoldout }
		);
		expect(consumed.store.canRead).toBe(false);
		await consumed.store.readHoldout();
		expect(readHoldout).not.toHaveBeenCalled();
	});

	it('refuses a read when the server says the holdout was read, even without a stored result', async () => {
		const readHoldout = vi.fn(async () => read);
		const { store } = await opened(
			{ ...candidateState(), freeze, holdout: holdout({ status: 'read', read_at: 5_000 }) },
			{ readHoldout }
		);
		expect(store.canRead).toBe(false);
		await store.readHoldout();
		expect(readHoldout).not.toHaveBeenCalled();
	});

	it('refuses a read when a result is already stored, even if the status looks unread', async () => {
		const readHoldout = vi.fn(async () => read);
		const { store } = await opened(
			{ ...candidateState(), freeze, holdout_read: read },
			{ readHoldout }
		);
		expect(store.canRead).toBe(false);
		await store.readHoldout();
		expect(readHoldout).not.toHaveBeenCalled();
	});

	it('reads once, then shows the stored result the server returns', async () => {
		let served: VerdictState = { ...candidateState(), freeze };
		const getVerdictState = vi.fn(async () => served);
		const readHoldout = vi.fn(async () => {
			served = {
				...served,
				holdout: holdout({ status: 'read', read_at: 5_000 }),
				holdout_read: read
			};
			return read;
		});
		const store = new VerdictStore(api({ getVerdictState, readHoldout }));
		await store.open('a');
		expect(store.canRead).toBe(true);
		await store.readHoldout();
		expect(readHoldout).toHaveBeenCalledWith('a', 'f1');
		expect(store.state?.holdout_read).toEqual(read);
		expect(store.canRead).toBe(false);
		await store.readHoldout();
		expect(readHoldout).toHaveBeenCalledTimes(1);
	});

	it('re-syncs after a failed read, since a timeout can hide a read that happened', async () => {
		let served: VerdictState = { ...candidateState(), freeze };
		const getVerdictState = vi.fn(async () => served);
		const readHoldout = vi.fn(async () => {
			served = {
				...served,
				holdout: holdout({ status: 'read', read_at: 5_000 }),
				holdout_read: read
			};
			throw new ApiError('timeout', 'The request timed out');
		});
		const store = new VerdictStore(api({ getVerdictState, readHoldout }));
		await store.open('a');
		await store.readHoldout();
		expect(store.readStatus).toBe('error');
		expect(store.state?.holdout?.status).toBe('read');
		expect(store.state?.holdout_read).toEqual(read);
		expect(store.canRead).toBe(false);
	});

	it('loads forward results only when rules are frozen', async () => {
		const getForward = vi.fn(async () => ({
			freeze,
			start: 2_000,
			end: null,
			bars: 0,
			waiting: true,
			rules: [],
			caveat: 'c',
			sharpe_se_annualised_iid: null
		}));
		const unfrozen = await opened(candidateState(), { getForward });
		await unfrozen.store.loadForward();
		expect(getForward).not.toHaveBeenCalled();
		const { store } = await opened({ ...candidateState(), freeze }, { getForward });
		await store.loadForward();
		expect(store.forward?.waiting).toBe(true);
	});

	it('loads the ledger on demand', async () => {
		const getVerdictLedger = vi.fn(async () => ({
			intact: true,
			total_entries: 2,
			trials: { dataset: 16, total: 16, keys: [] },
			entries: []
		}));
		const { store } = await opened(candidateState(), { getVerdictLedger });
		await store.loadLedger();
		expect(store.ledger?.trials.dataset).toBe(16);
		expect(store.ledgerStatus).toBe('ready');
	});
});
