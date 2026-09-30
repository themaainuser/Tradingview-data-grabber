/**
 * Runtime validation of the verdict engine's payloads.
 *
 * Besides shape, these check the invariants the UI relies on so it can never draw a contradictory
 * verdict: a rule that did not pass the trade-count gate has no statistics, statistics exist only
 * when some rule passed, and a CANDIDATE label needs at least one candidate rule.
 */
import type {
	ForwardResult,
	HoldoutInfo,
	HoldoutResult,
	LedgerView,
	RuleStatus,
	RuleWindow,
	VerdictCosts,
	VerdictDefaults,
	VerdictEvidence,
	VerdictFreeze,
	VerdictLabel,
	VerdictLedgerSummary,
	VerdictReport,
	VerdictRule,
	VerdictState,
	VerdictStatistics
} from './contracts';
import { arr, bool, fail, nullableNum, nullableStr, num, numbers, obj, str } from './validate';

const VERDICT_LABELS: readonly VerdictLabel[] = [
	'INSUFFICIENT_DATA',
	'INDISTINGUISHABLE_FROM_LUCK',
	'CANDIDATE'
];
const RULE_STATUSES: readonly RuleStatus[] = [
	'NEVER_TRADES',
	'INSUFFICIENT_TRADES',
	'PASSED_GATE',
	'ERROR'
];

function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
	const text = str(value, path);
	if (!allowed.includes(text as T)) fail(path, `one of ${allowed.join(', ')}`);
	return text as T;
}

const strings = (value: unknown, path: string) =>
	arr(value, path).map((v, i) => str(v, `${path}[${i}]`));

function parameters(value: unknown, path: string): Record<string, number> {
	const out: Record<string, number> = {};
	for (const [key, raw] of Object.entries(obj(value, path))) out[key] = num(raw, `${path}.${key}`);
	return out;
}

function costs(value: unknown, path: string): VerdictCosts {
	const o = obj(value, path);
	return {
		fee_bps_per_side: num(o.fee_bps_per_side, `${path}.fee_bps_per_side`),
		spread_bps: num(o.spread_bps, `${path}.spread_bps`),
		slippage_k: num(o.slippage_k, `${path}.slippage_k`)
	};
}

export function parseHoldoutInfo(value: unknown, path = 'holdout'): HoldoutInfo {
	const o = obj(value, path);
	return {
		fraction: num(o.fraction, `${path}.fraction`),
		start: num(o.start, `${path}.start`),
		end: num(o.end, `${path}.end`),
		bars: num(o.bars, `${path}.bars`),
		sealed_at: num(o.sealed_at, `${path}.sealed_at`),
		status: oneOf(o.status, ['unread', 'read'] as const, `${path}.status`),
		read_at: nullableNum(o.read_at, `${path}.read_at`)
	};
}

function ledgerSummary(value: unknown, path: string): VerdictLedgerSummary {
	const o = obj(value, path);
	return {
		trials_dataset: num(o.trials_dataset, `${path}.trials_dataset`),
		trials_total: num(o.trials_total, `${path}.trials_total`),
		runs_dataset: num(o.runs_dataset, `${path}.runs_dataset`),
		intact: bool(o.intact, `${path}.intact`)
	};
}

function evidence(value: unknown, path: string): VerdictEvidence {
	const o = obj(value, path);
	const n = (key: string) => nullableNum(o[key], `${path}.${key}`);
	const sensitivity = obj(o.dsr_sensitivity, `${path}.dsr_sensitivity`);
	const side = (key: 'low_n' | 'high_n') => {
		const s = obj(sensitivity[key], `${path}.dsr_sensitivity.${key}`);
		return {
			n: nullableNum(s.n, `${path}.dsr_sensitivity.${key}.n`),
			dsr: nullableNum(s.dsr, `${path}.dsr_sensitivity.${key}.dsr`)
		};
	};
	const breakEven = obj(o.break_even, `${path}.break_even`);
	const checks = obj(o.checks, `${path}.checks`);
	const be = (key: string) => nullableNum(breakEven[key], `${path}.break_even.${key}`);
	return {
		sharpe: n('sharpe'),
		sharpe_se: n('sharpe_se'),
		mean_trade_return_pct: n('mean_trade_return_pct'),
		adjusted_p: n('adjusted_p'),
		dsr: n('dsr'),
		dsr_sensitivity: { low_n: side('low_n'), high_n: side('high_n') },
		break_even: {
			round_trip_bps: be('round_trip_bps'),
			base_round_trip_bps: be('base_round_trip_bps'),
			multiple: be('multiple')
		},
		stress: arr(o.stress, `${path}.stress`).map((raw, i) => {
			const s = obj(raw, `${path}.stress[${i}]`);
			const v = (key: string) => nullableNum(s[key], `${path}.stress[${i}].${key}`);
			return {
				multiplier: num(s.multiplier, `${path}.stress[${i}].multiplier`),
				sharpe: v('sharpe'),
				mean_trade_return_pct: v('mean_trade_return_pct'),
				total_return_pct: v('total_return_pct')
			};
		}),
		checks: {
			bootstrap: bool(checks.bootstrap, `${path}.checks.bootstrap`),
			dsr: bool(checks.dsr, `${path}.checks.dsr`),
			stress: bool(checks.stress, `${path}.checks.stress`)
		},
		candidate: bool(o.candidate, `${path}.candidate`)
	};
}

function verdictRule(value: unknown, path: string): VerdictRule {
	const o = obj(value, path);
	const status = oneOf(o.status, RULE_STATUSES, `${path}.status`);
	const hasEvidence = o.evidence !== null && o.evidence !== undefined;
	if (hasEvidence && status !== 'PASSED_GATE')
		fail(`${path}.evidence`, 'null unless the rule passed the gate');
	if (!hasEvidence && status === 'PASSED_GATE')
		fail(`${path}.evidence`, 'present for a rule that passed the gate');
	return {
		id: str(o.id, `${path}.id`),
		family: str(o.family, `${path}.family`),
		name: str(o.name, `${path}.name`),
		parameters: parameters(o.parameters, `${path}.parameters`),
		status,
		trades: num(o.trades, `${path}.trades`),
		closed_trades: num(o.closed_trades, `${path}.closed_trades`),
		exposure_pct: num(o.exposure_pct, `${path}.exposure_pct`),
		error: nullableStr(o.error, `${path}.error`),
		evidence: hasEvidence ? evidence(o.evidence, `${path}.evidence`) : null
	};
}

function verdictStatistics(value: unknown): VerdictStatistics {
	const o = obj(value, 'statistics');
	const en = obj(o.effective_n, 'statistics.effective_n');
	const rc = obj(o.reality_check, 'statistics.reality_check');
	let pbo: VerdictStatistics['pbo'] = null;
	if (o.pbo !== null && o.pbo !== undefined) {
		const p = obj(o.pbo, 'statistics.pbo');
		pbo = {
			value: nullableNum(p.value, 'statistics.pbo.value'),
			blocks: num(p.blocks, 'statistics.pbo.blocks'),
			combinations: num(p.combinations, 'statistics.pbo.combinations'),
			rules: num(p.rules, 'statistics.pbo.rules'),
			noisy: bool(p.noisy, 'statistics.pbo.noisy'),
			caveat: str(p.caveat, 'statistics.pbo.caveat')
		};
	}
	const e = (key: string) => num(en[key], `statistics.effective_n.${key}`);
	const r = (key: string) => num(rc[key], `statistics.reality_check.${key}`);
	return {
		effective_n: {
			estimate: e('estimate'),
			low: e('low'),
			high: e('high'),
			level: e('level'),
			rules_used: e('rules_used'),
			ledger_trials: e('ledger_trials'),
			scaled_estimate: e('scaled_estimate')
		},
		reality_check: {
			statistic: str(rc.statistic, 'statistics.reality_check.statistic'),
			best_rule: nullableStr(rc.best_rule, 'statistics.reality_check.best_rule'),
			p_value: nullableNum(rc.p_value, 'statistics.reality_check.p_value'),
			alpha: r('alpha'),
			rejected: bool(rc.rejected, 'statistics.reality_check.rejected'),
			rules_tested: r('rules_tested'),
			replicates: r('replicates'),
			mean_block_length: r('mean_block_length'),
			seed: r('seed')
		},
		pbo,
		pbo_unavailable: nullableStr(o.pbo_unavailable, 'statistics.pbo_unavailable')
	};
}

export function parseVerdictReport(json: unknown): VerdictReport {
	const o = obj(json, 'report');
	const dataset = obj(o.dataset, 'dataset');
	const verdict = obj(o.verdict, 'verdict');
	const settings = obj(o.settings, 'settings');
	const boot = obj(settings.bootstrap, 'settings.bootstrap');
	const data = obj(o.data, 'data');
	const holdout = obj(data.holdout, 'data.holdout');
	const uncertainty = obj(o.uncertainty, 'uncertainty');
	const integrity = obj(o.integrity, 'integrity');
	const probe = obj(integrity.lookahead_probe, 'integrity.lookahead_probe');
	const gap = obj(integrity.close_to_open_gap_bps, 'integrity.close_to_open_gap_bps');

	const label = oneOf(verdict.label, VERDICT_LABELS, 'verdict.label');
	const rules = arr(o.rules, 'rules').map((r, i) => verdictRule(r, `rules[${i}]`));
	const passed = rules.filter((r) => r.status === 'PASSED_GATE');
	const candidates = rules.filter((r) => r.evidence?.candidate);
	const statistics =
		o.statistics === null || o.statistics === undefined ? null : verdictStatistics(o.statistics);

	if (label === 'INSUFFICIENT_DATA' && (passed.length > 0 || statistics !== null)) {
		fail('verdict.label', 'INSUFFICIENT_DATA only when no rule passed the gate');
	}
	if (label !== 'INSUFFICIENT_DATA' && passed.length === 0) {
		fail('verdict.label', 'INSUFFICIENT_DATA when no rule passed the gate');
	}
	if (label === 'CANDIDATE' && candidates.length === 0)
		fail('verdict.label', 'CANDIDATE only with a candidate rule');
	if (label !== 'CANDIDATE' && candidates.length > 0)
		fail('verdict.label', 'CANDIDATE when a rule is a candidate');

	const gapValue = (key: string) => nullableNum(gap[key], `integrity.close_to_open_gap_bps.${key}`);
	return {
		run_id: str(o.run_id, 'run_id'),
		created_at: num(o.created_at, 'created_at'),
		dataset: {
			id: str(dataset.id, 'dataset.id'),
			symbol: str(dataset.symbol, 'dataset.symbol'),
			timeframe: nullableStr(dataset.timeframe, 'dataset.timeframe'),
			path: str(dataset.path, 'dataset.path')
		},
		verdict: {
			label,
			headline: str(verdict.headline, 'verdict.headline'),
			reasons: strings(verdict.reasons, 'verdict.reasons')
		},
		settings: {
			min_trades: num(settings.min_trades, 'settings.min_trades'),
			costs: costs(settings.costs, 'settings.costs'),
			periods_per_year: num(settings.periods_per_year, 'settings.periods_per_year'),
			periods_per_year_inferred: bool(
				settings.periods_per_year_inferred,
				'settings.periods_per_year_inferred'
			),
			alpha: num(settings.alpha, 'settings.alpha'),
			dsr_threshold: num(settings.dsr_threshold, 'settings.dsr_threshold'),
			stress_multipliers: numbers(settings.stress_multipliers, 'settings.stress_multipliers'),
			bootstrap: {
				replicates: num(boot.replicates, 'settings.bootstrap.replicates'),
				mean_block_length: num(boot.mean_block_length, 'settings.bootstrap.mean_block_length'),
				seed: num(boot.seed, 'settings.bootstrap.seed')
			}
		},
		data: {
			bars_total: num(data.bars_total, 'data.bars_total'),
			research_bars: num(data.research_bars, 'data.research_bars'),
			research_start: num(data.research_start, 'data.research_start'),
			research_end: num(data.research_end, 'data.research_end'),
			forward_bars: num(data.forward_bars, 'data.forward_bars'),
			holdout: {
				...parseHoldoutInfo(holdout, 'data.holdout'),
				created_now: bool(holdout.created_now, 'data.holdout.created_now')
			}
		},
		ledger: ledgerSummary(o.ledger, 'ledger'),
		rules,
		statistics,
		uncertainty: {
			research_bars: num(uncertainty.research_bars, 'uncertainty.research_bars'),
			sharpe_se_annualised_iid: nullableNum(
				uncertainty.sharpe_se_annualised_iid,
				'uncertainty.sharpe_se_annualised_iid'
			),
			holdout_bars: num(uncertainty.holdout_bars, 'uncertainty.holdout_bars'),
			holdout_sharpe_se_annualised_iid: nullableNum(
				uncertainty.holdout_sharpe_se_annualised_iid,
				'uncertainty.holdout_sharpe_se_annualised_iid'
			),
			note: str(uncertainty.note, 'uncertainty.note')
		},
		integrity: {
			fill_model: str(integrity.fill_model, 'integrity.fill_model'),
			signal_shift_verified: bool(
				integrity.signal_shift_verified,
				'integrity.signal_shift_verified'
			),
			lookahead_probe: {
				passed: bool(probe.passed, 'integrity.lookahead_probe.passed'),
				rules_checked: num(probe.rules_checked, 'integrity.lookahead_probe.rules_checked'),
				truncation_bar: num(probe.truncation_bar, 'integrity.lookahead_probe.truncation_bar')
			},
			close_to_open_gap_bps: {
				mean_abs: gapValue('mean_abs'),
				p99_abs: gapValue('p99_abs'),
				max_abs: gapValue('max_abs')
			},
			research_fingerprint: str(integrity.research_fingerprint, 'integrity.research_fingerprint')
		},
		notes: strings(o.notes, 'notes')
	};
}

export function parseFreeze(value: unknown, path = 'freeze'): VerdictFreeze {
	const o = obj(value, path);
	return {
		id: str(o.id, `${path}.id`),
		run_id: str(o.run_id, `${path}.run_id`),
		rule_ids: strings(o.rule_ids, `${path}.rule_ids`),
		rules: arr(o.rules, `${path}.rules`).map((raw, i) => {
			const r = obj(raw, `${path}.rules[${i}]`);
			return {
				id: str(r.id, `${path}.rules[${i}].id`),
				name: str(r.name, `${path}.rules[${i}].name`),
				family: str(r.family, `${path}.rules[${i}].family`),
				parameters: parameters(r.parameters, `${path}.rules[${i}].parameters`)
			};
		}),
		frozen_at: num(o.frozen_at, `${path}.frozen_at`),
		forward_start: num(o.forward_start, `${path}.forward_start`),
		hash: str(o.hash, `${path}.hash`)
	};
}

function ruleWindows(value: unknown, path: string): RuleWindow[] {
	return arr(value, path).map((raw, i) => {
		const r = obj(raw, `${path}[${i}]`);
		const n = (key: string) => nullableNum(r[key], `${path}[${i}].${key}`);
		return {
			id: str(r.id, `${path}[${i}].id`),
			name: str(r.name, `${path}[${i}].name`),
			trades: num(r.trades, `${path}[${i}].trades`),
			closed_trades: num(r.closed_trades, `${path}[${i}].closed_trades`),
			exposure_pct: num(r.exposure_pct, `${path}[${i}].exposure_pct`),
			net_return_pct: n('net_return_pct'),
			sharpe: n('sharpe'),
			sharpe_se: n('sharpe_se'),
			mean_trade_return_pct: n('mean_trade_return_pct'),
			buy_hold_return_pct: n('buy_hold_return_pct')
		};
	});
}

export function parseHoldoutResult(value: unknown, path = 'holdout_read'): HoldoutResult {
	const o = obj(value, path);
	return {
		freeze_id: str(o.freeze_id, `${path}.freeze_id`),
		read_at: num(o.read_at, `${path}.read_at`),
		start: num(o.start, `${path}.start`),
		end: num(o.end, `${path}.end`),
		bars: num(o.bars, `${path}.bars`),
		rules: ruleWindows(o.rules, `${path}.rules`),
		caveat: str(o.caveat, `${path}.caveat`),
		sharpe_se_annualised_iid: nullableNum(
			o.sharpe_se_annualised_iid,
			`${path}.sharpe_se_annualised_iid`
		)
	};
}

export function parseForward(json: unknown): ForwardResult {
	const o = obj(json, 'forward');
	return {
		freeze: parseFreeze(o.freeze, 'forward.freeze'),
		start: num(o.start, 'forward.start'),
		end: nullableNum(o.end, 'forward.end'),
		bars: num(o.bars, 'forward.bars'),
		waiting: bool(o.waiting, 'forward.waiting'),
		rules: ruleWindows(o.rules, 'forward.rules'),
		caveat: str(o.caveat, 'forward.caveat'),
		sharpe_se_annualised_iid: nullableNum(
			o.sharpe_se_annualised_iid,
			'forward.sharpe_se_annualised_iid'
		)
	};
}

function verdictDefaults(value: unknown): VerdictDefaults {
	const o = obj(value, 'defaults');
	return {
		min_trades: num(o.min_trades, 'defaults.min_trades'),
		holdout_fraction: num(o.holdout_fraction, 'defaults.holdout_fraction'),
		costs: costs(o.costs, 'defaults.costs'),
		cost_notes: arr(o.cost_notes, 'defaults.cost_notes').map((raw, i) => {
			const c = obj(raw, `defaults.cost_notes[${i}]`);
			return {
				field: str(c.field, `defaults.cost_notes[${i}].field`),
				value: num(c.value, `defaults.cost_notes[${i}].value`),
				basis: str(c.basis, `defaults.cost_notes[${i}].basis`)
			};
		}),
		bootstrap_replicates: num(o.bootstrap_replicates, 'defaults.bootstrap_replicates'),
		alpha: num(o.alpha, 'defaults.alpha'),
		dsr_threshold: num(o.dsr_threshold, 'defaults.dsr_threshold'),
		stress_multipliers: numbers(o.stress_multipliers, 'defaults.stress_multipliers')
	};
}

export function parseVerdictState(json: unknown): VerdictState {
	const o = obj(json, 'state');
	const dataset = obj(o.dataset, 'dataset');
	const sealed = bool(o.sealed, 'sealed');
	const hasHoldout = o.holdout !== null && o.holdout !== undefined;
	if (sealed !== hasHoldout)
		fail('holdout', sealed ? 'present when sealed' : 'null when not sealed');
	const holdout = hasHoldout ? parseHoldoutInfo(o.holdout, 'holdout') : null;
	const hasRead = o.holdout_read !== null && o.holdout_read !== undefined;
	if (hasRead && holdout?.status !== 'read')
		fail('holdout_read', 'only present once the holdout is read');
	return {
		dataset: {
			id: str(dataset.id, 'dataset.id'),
			symbol: str(dataset.symbol, 'dataset.symbol'),
			timeframe: nullableStr(dataset.timeframe, 'dataset.timeframe'),
			path: str(dataset.path, 'dataset.path'),
			rows: num(dataset.rows, 'dataset.rows')
		},
		sealed,
		holdout,
		ledger: ledgerSummary(o.ledger, 'ledger'),
		latest: o.latest === null || o.latest === undefined ? null : parseVerdictReport(o.latest),
		freeze: o.freeze === null || o.freeze === undefined ? null : parseFreeze(o.freeze),
		holdout_read: hasRead ? parseHoldoutResult(o.holdout_read) : null,
		defaults: verdictDefaults(o.defaults)
	};
}

export function parseLedger(json: unknown): LedgerView {
	const o = obj(json, 'ledger');
	const trials = obj(o.trials, 'ledger.trials');
	return {
		intact: bool(o.intact, 'ledger.intact'),
		total_entries: num(o.total_entries, 'ledger.total_entries'),
		trials: {
			dataset: num(trials.dataset, 'ledger.trials.dataset'),
			total: num(trials.total, 'ledger.trials.total'),
			keys: arr(trials.keys, 'ledger.trials.keys').map((raw, i) => {
				const k = obj(raw, `ledger.trials.keys[${i}]`);
				return {
					key: str(k.key, `ledger.trials.keys[${i}].key`),
					rule_id: str(k.rule_id, `ledger.trials.keys[${i}].rule_id`),
					first_seen: num(k.first_seen, `ledger.trials.keys[${i}].first_seen`),
					runs: num(k.runs, `ledger.trials.keys[${i}].runs`)
				};
			})
		},
		entries: arr(o.entries, 'ledger.entries').map((raw, i) => {
			const e = obj(raw, `ledger.entries[${i}]`);
			return {
				seq: num(e.seq, `ledger.entries[${i}].seq`),
				type: str(e.type, `ledger.entries[${i}].type`),
				at: str(e.at, `ledger.entries[${i}].at`),
				hash: str(e.hash, `ledger.entries[${i}].hash`),
				prev: str(e.prev, `ledger.entries[${i}].prev`),
				summary: str(e.summary, `ledger.entries[${i}].summary`)
			};
		})
	};
}
