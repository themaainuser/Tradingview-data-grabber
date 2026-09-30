import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';
import { ApiError } from './errors';
import {
	freeze,
	holdout,
	holdoutResult,
	captureRules,
	passedRule,
	report,
	rule,
	verdictState
} from '$lib/testing/verdict-fixtures';
import {
	parseForward,
	parseFreeze,
	parseHoldoutResult,
	parseLedger,
	parseVerdictReport,
	parseVerdictState
} from './verdict';

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

describe('parseVerdictReport', () => {
	it('accepts the real-capture shape: 16 gated rules, no statistics', () => {
		const parsed = parseVerdictReport(report());
		expect(parsed.verdict.label).toBe('INSUFFICIENT_DATA');
		expect(parsed.rules).toHaveLength(16);
		expect(parsed.rules.every((r) => r.evidence === null)).toBe(true);
		expect(parsed.statistics).toBeNull();
		expect(parsed.rules.filter((r) => r.status === 'NEVER_TRADES')).toHaveLength(3);
	});

	it('accepts a CANDIDATE report with evidence and statistics', () => {
		const parsed = parseVerdictReport(
			report('CANDIDATE', [passedRule('sma-5-20'), rule('sma-10-20')])
		);
		expect(parsed.rules[0].evidence?.candidate).toBe(true);
		expect(parsed.statistics?.effective_n.low).toBeLessThan(parsed.statistics!.effective_n.high);
	});

	it('accepts an INDISTINGUISHABLE report whose rules passed the gate but are not candidates', () => {
		const notCandidate = passedRule('sma-5-20', {
			candidate: false,
			adjusted_p: 0.41,
			checks: { bootstrap: false, dsr: true, stress: true }
		});
		const parsed = parseVerdictReport(report('INDISTINGUISHABLE_FROM_LUCK', [notCandidate]));
		expect(parsed.verdict.label).toBe('INDISTINGUISHABLE_FROM_LUCK');
	});

	it('keeps nulls for statistics the backend could not compute', () => {
		const body = report('CANDIDATE', [passedRule('sma-5-20', { dsr: null, adjusted_p: null })]);
		const parsed = parseVerdictReport(clone(body));
		expect(parsed.rules[0].evidence?.dsr).toBeNull();
	});

	const bad: [string, (r: ReturnType<typeof report>) => unknown, RegExp][] = [
		[
			'a gated rule that carries statistics',
			(r) => {
				r.rules[0].evidence = passedRule('sma-5-20').evidence;
				return r;
			},
			/evidence/
		],
		[
			'a rule that passed the gate but has no statistics',
			(r) => {
				r.rules[0].status = 'PASSED_GATE';
				return r;
			},
			/evidence/
		],
		[
			'INSUFFICIENT_DATA with a rule that passed the gate',
			(r) => {
				r.rules[0] = passedRule('sma-5-20');
				return r;
			},
			/INSUFFICIENT_DATA/
		],
		[
			'statistics on an INSUFFICIENT_DATA run',
			(r) => ({ ...r, statistics: report('CANDIDATE', [passedRule('sma-5-20')]).statistics }),
			/INSUFFICIENT_DATA/
		],
		[
			'a verdict other than INSUFFICIENT_DATA when nothing passed the gate',
			(r) => ({ ...r, verdict: { ...r.verdict, label: 'INDISTINGUISHABLE_FROM_LUCK' } }),
			/INSUFFICIENT_DATA/
		],
		[
			'CANDIDATE without a candidate rule',
			(r) => ({
				...r,
				verdict: { ...r.verdict, label: 'CANDIDATE' },
				rules: [passedRule('sma-5-20', { candidate: false })],
				statistics: report('CANDIDATE', [passedRule('sma-5-20')]).statistics
			}),
			/CANDIDATE/
		],
		[
			'a candidate rule under a non-CANDIDATE label',
			(r) => ({
				...r,
				verdict: { ...r.verdict, label: 'INDISTINGUISHABLE_FROM_LUCK' },
				rules: [passedRule('sma-5-20')],
				statistics: report('CANDIDATE', [passedRule('sma-5-20')]).statistics
			}),
			/CANDIDATE/
		],
		[
			'an unknown label',
			(r) => ({ ...r, verdict: { ...r.verdict, label: 'WINNER' } }),
			/verdict\.label/
		],
		[
			'an unknown rule status',
			(r) => {
				(r.rules[0] as { status: string }).status = 'GREAT';
				return r;
			},
			/status/
		],
		[
			'a non-finite trade count',
			(r) => {
				(r.rules[0] as { trades: unknown }).trades = 'many';
				return r;
			},
			/trades/
		],
		['a missing integrity block', (r) => ({ ...r, integrity: undefined }), /integrity/],
		[
			'a non-boolean chain flag',
			(r) => ({ ...r, ledger: { ...r.ledger, intact: 'yes' } }),
			/intact/
		]
	];
	it.each(bad)('rejects %s', (_name, mutate, pattern) => {
		const body = mutate(clone(report()));
		expect(() => parseVerdictReport(body)).toThrow(ApiError);
		expect(() => parseVerdictReport(body)).toThrow(pattern);
	});

	it('never exposes a rank or score field, whatever the backend sends', () => {
		const body = clone(report('CANDIDATE', [passedRule('sma-5-20')])) as unknown as {
			rules: Record<string, unknown>[];
		};
		body.rules[0].rank = 1;
		const parsed = parseVerdictReport(body);
		expect(JSON.stringify(parsed)).not.toMatch(/"rank"/);
	});
});

describe('parseVerdictState', () => {
	it('accepts an unsealed dataset with defaults and nothing else', () => {
		const parsed = parseVerdictState(verdictState());
		expect(parsed.sealed).toBe(false);
		expect(parsed.holdout).toBeNull();
		expect(parsed.latest).toBeNull();
		expect(parsed.defaults.costs.fee_bps_per_side).toBe(10);
		expect(parsed.defaults.cost_notes).toHaveLength(3);
	});

	it('accepts a sealed, frozen and read state', () => {
		const parsed = parseVerdictState(
			verdictState({
				sealed: true,
				holdout: holdout({ status: 'read', read_at: 1_790_200_000 }),
				latest: report('CANDIDATE', [passedRule('sma-5-20')]),
				freeze,
				holdout_read: holdoutResult()
			})
		);
		expect(parsed.freeze?.rule_ids).toEqual(['sma-5-20']);
		expect(parsed.holdout_read?.bars).toBe(200);
	});

	it.each([
		['sealed without a holdout', { sealed: true, holdout: null }, /holdout/],
		['a holdout without being sealed', { sealed: false, holdout: holdout() }, /holdout/],
		[
			'a stored read while the holdout is unread',
			{ sealed: true, holdout: holdout(), holdout_read: holdoutResult() },
			/holdout_read/
		]
	])('rejects %s', (_name, patch, pattern) => {
		expect(() => parseVerdictState(clone({ ...verdictState(), ...patch }))).toThrow(pattern);
	});
});

describe('freeze, holdout read, forward and ledger', () => {
	it('parses a freeze and rejects a malformed one', () => {
		expect(parseFreeze(freeze).hash).toBe('deadbeefcafe');
		expect(() => parseFreeze({ ...freeze, rule_ids: 'sma-5-20' })).toThrow(/rule_ids/);
		expect(() => parseFreeze({ ...freeze, frozen_at: 'now' })).toThrow(/frozen_at/);
	});

	it('parses a holdout result, keeping null statistics', () => {
		const result = holdoutResult();
		result.rules[0].sharpe = null;
		expect(parseHoldoutResult(clone(result)).rules[0].sharpe).toBeNull();
		expect(() => parseHoldoutResult({ ...result, caveat: 5 })).toThrow(/caveat/);
	});

	it('parses forward results and the waiting state', () => {
		const waiting = {
			freeze,
			start: 1_790_000_000,
			end: null,
			bars: 0,
			waiting: true,
			rules: [],
			caveat: 'c',
			sharpe_se_annualised_iid: null
		};
		expect(parseForward(waiting).waiting).toBe(true);
		expect(() => parseForward({ ...waiting, waiting: 'yes' })).toThrow(/waiting/);
	});

	it('parses the ledger view', () => {
		const view = {
			intact: true,
			total_entries: 2,
			trials: {
				dataset: 16,
				total: 16,
				keys: [{ key: 'a::sma-5-20', rule_id: 'sma-5-20', first_seen: 1, runs: 2 }]
			},
			entries: [
				{ seq: 1, type: 'run', at: '2026-09-30T00:00:00Z', hash: 'h', prev: 'p', summary: 'Run 1' }
			]
		};
		expect(parseLedger(view).trials.keys[0].runs).toBe(2);
		expect(() => parseLedger({ ...view, intact: null })).toThrow(/intact/);
	});
});

describe('api client: verdict', () => {
	it('encodes ids in the state and ledger URLs and sends the ledger limit', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async (url) =>
			String(url).includes('/ledger')
				? json({
						intact: true,
						total_entries: 0,
						trials: { dataset: 0, total: 0, keys: [] },
						entries: []
					})
				: json(verdictState())
		);
		const client = createApiClient({ fetch });
		await client.getVerdictState('a/b c');
		await client.getVerdictLedger('a/b c', { limit: 50.9 });
		expect(fetch.mock.calls[0][0]).toBe('/api/verdict/a%2Fb%20c');
		expect(fetch.mock.calls[1][0]).toBe('/api/verdict/a%2Fb%20c/ledger?limit=50');
	});

	it('posts the run as JSON and never retries it, even on a 503', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json({ detail: 'busy' }, 503));
		const error = await createApiClient({ fetch, retryDelayMs: 1 })
			.runVerdict({
				dataset_id: 'abc',
				min_trades: 30,
				costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
				periods_per_year: null
			})
			.catch((e) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect(fetch).toHaveBeenCalledTimes(1);
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe('/api/verdict/run');
		expect(init?.method).toBe('POST');
		expect(JSON.parse(String(init?.body))).toMatchObject({
			dataset_id: 'abc',
			periods_per_year: null
		});
	});

	it('never retries a holdout read and surfaces the refusal', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () =>
			json({ detail: 'holdout already read on 2026-09-30T00:00:00Z; it cannot be read again' }, 409)
		);
		const error = await createApiClient({ fetch, retryDelayMs: 1 })
			.readHoldout('abc', 'f1')
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'http', status: 409 });
		expect(error.message).toContain('cannot be read again');
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ freeze_id: 'f1' });
	});

	it('seals with the chosen share and returns the parsed holdout', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () =>
			json({ holdout: holdout({ fraction: 0.25 }) })
		);
		const result = await createApiClient({ fetch }).sealHoldout('abc', 0.25);
		expect(result.fraction).toBe(0.25);
		expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ holdout_fraction: 0.25 });
	});

	it('rejects a seal response without a holdout instead of inventing one', async () => {
		const error = await createApiClient({ fetch: async () => json({}) })
			.sealHoldout('abc', 0.2)
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'contract' });
	});

	it('sends the freeze body and parses the freeze', async () => {
		const fetch = vi.fn<typeof globalThis.fetch>(async () => json(freeze));
		const result = await createApiClient({ fetch }).freezeRules('abc', {
			run_id: 'run-1',
			rule_ids: ['sma-5-20']
		});
		expect(result.id).toBe('f1');
		expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
			run_id: 'run-1',
			rule_ids: ['sma-5-20']
		});
		expect(fetch.mock.calls[0][0]).toBe('/api/verdict/abc/freeze');
	});

	it('rejects a verdict body that contradicts itself instead of rendering it', async () => {
		const contradictory = clone(report());
		contradictory.verdict.label = 'CANDIDATE';
		const error = await createApiClient({ fetch: async () => json(contradictory) })
			.runVerdict({
				dataset_id: 'abc',
				min_trades: 30,
				costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
				periods_per_year: null
			})
			.catch((e) => e);
		expect(error).toMatchObject({ kind: 'contract' });
	});

	it('uses the gate statuses from the fixtures consistently', () => {
		expect(captureRules().filter((r) => r.trades >= 30)).toHaveLength(0);
	});
});
