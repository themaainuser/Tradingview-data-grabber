/**
 * Test-only builders for verdict payloads, in the exact JSON shape the backend returns.
 * Never imported by app code.
 */
import type {
	HoldoutInfo,
	HoldoutResult,
	VerdictEvidence,
	VerdictFreeze,
	VerdictReport,
	VerdictRule,
	VerdictState
} from '$lib/api/contracts';

export const holdout = (overrides: Partial<HoldoutInfo> = {}): HoldoutInfo => ({
	fraction: 0.2,
	start: 1_000,
	end: 2_000,
	bars: 200,
	sealed_at: 2_100,
	status: 'unread',
	read_at: null,
	...overrides
});

export const evidence = (overrides: Partial<VerdictEvidence> = {}): VerdictEvidence => ({
	sharpe: 1.1,
	sharpe_se: 2.9,
	mean_trade_return_pct: 0.31,
	adjusted_p: 0.012,
	dsr: 0.97,
	dsr_sensitivity: { low_n: { n: 2.1, dsr: 0.98 }, high_n: { n: 6.4, dsr: 0.96 } },
	break_even: { round_trip_bps: 61, base_round_trip_bps: 22, multiple: 2.8 },
	stress: [
		{ multiplier: 1, sharpe: 1.1, mean_trade_return_pct: 0.31, total_return_pct: 14 },
		{ multiplier: 1.5, sharpe: 0.8, mean_trade_return_pct: 0.2, total_return_pct: 9 },
		{ multiplier: 2, sharpe: 0.5, mean_trade_return_pct: 0.09, total_return_pct: 4 }
	],
	checks: { bootstrap: true, dsr: true, stress: true },
	candidate: true,
	...overrides
});

/** The fixed 16-rule grid in the backend's order. */
export const GRID: {
	id: string;
	family: string;
	name: string;
	parameters: Record<string, number>;
}[] = [
	...[
		[5, 20],
		[10, 20],
		[5, 50],
		[10, 50],
		[20, 50],
		[5, 100],
		[20, 100]
	].map(([fast, slow]) => ({
		id: `sma-${fast}-${slow}`,
		family: 'SMA crossover',
		name: `SMA ${fast}/${slow}`,
		parameters: { fast, slow }
	})),
	...[20, 25, 30].flatMap((entry) =>
		[50, 55, 60].map((exit) => ({
			id: `rsi-${entry}-${exit}`,
			family: 'RSI mean reversion',
			name: `RSI ${entry}/${exit}`,
			parameters: { entry, exit }
		}))
	)
];

/** Entries per rule measured on the real 1,000-bar hourly BTC capture: nothing reaches 30. */
export const CAPTURE_TRADES = [29, 25, 22, 15, 14, 9, 6, 0, 0, 0, 1, 1, 1, 6, 6, 6];

export function rule(id: string, overrides: Partial<VerdictRule> = {}): VerdictRule {
	const base = GRID.find((g) => g.id === id) ?? {
		id,
		family: 'SMA crossover',
		name: id.toUpperCase(),
		parameters: { fast: 5, slow: 20 }
	};
	return {
		...base,
		status: 'INSUFFICIENT_TRADES',
		trades: 4,
		closed_trades: 4,
		exposure_pct: 40,
		error: null,
		evidence: null,
		...overrides
	};
}

export const passedRule = (id: string, ev: Partial<VerdictEvidence> = {}): VerdictRule =>
	rule(id, {
		status: 'PASSED_GATE',
		trades: 64,
		closed_trades: 63,
		exposure_pct: 47,
		evidence: evidence(ev)
	});

/** All 16 rules as on the real capture: three never trade, the rest have too few trades. */
export const captureRules = (): VerdictRule[] =>
	GRID.map((g, i) =>
		rule(g.id, {
			status: CAPTURE_TRADES[i] === 0 ? 'NEVER_TRADES' : 'INSUFFICIENT_TRADES',
			trades: CAPTURE_TRADES[i],
			closed_trades: Math.max(0, CAPTURE_TRADES[i] - 1),
			exposure_pct: CAPTURE_TRADES[i] === 0 ? 0 : 40
		})
	);

export function report(
	label: VerdictReport['verdict']['label'] = 'INSUFFICIENT_DATA',
	rules: VerdictRule[] = captureRules(),
	overrides: Partial<VerdictReport> = {}
): VerdictReport {
	const insufficient = label === 'INSUFFICIENT_DATA';
	return {
		run_id: 'run-1',
		created_at: 1_790_000_000,
		dataset: {
			id: 'abc',
			symbol: 'BINANCE:BTCUSDT',
			timeframe: '60',
			path: 'BINANCE_BTCUSDT/60.csv'
		},
		verdict: {
			label,
			headline: insufficient
				? 'No rule reached 30 trades on 800 research bars (most: 29). Nothing can be concluded or ranked.'
				: label === 'CANDIDATE'
					? 'One rule passed the gate, the bootstrap, the DSR and the 1.5x cost stress.'
					: 'Rules traded enough to test, but none stands out from luck.',
			reasons: insufficient
				? ['Most trades by any rule: 29 (minimum 30).']
				: ['Adjusted p-value above 0.05.']
		},
		settings: {
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: 8760,
			periods_per_year_inferred: true,
			alpha: 0.05,
			dsr_threshold: 0.95,
			stress_multipliers: [1, 1.5, 2],
			bootstrap: { replicates: 2000, mean_block_length: 9, seed: 123456 }
		},
		data: {
			bars_total: 1000,
			research_bars: 800,
			research_start: 1_787_000_000,
			research_end: 1_789_900_000,
			forward_bars: 0,
			holdout: { ...holdout(), created_now: false }
		},
		ledger: { trials_dataset: 16, trials_total: 16, runs_dataset: 1, intact: true },
		rules,
		statistics: insufficient
			? null
			: {
					effective_n: {
						estimate: 3.2,
						low: 2.1,
						high: 6.4,
						level: 0.9,
						rules_used: 13,
						ledger_trials: 16,
						scaled_estimate: 3.2
					},
					reality_check: {
						statistic: 'studentised mean excess return over exposure-matched passive holding',
						best_rule: rules.find((r) => r.status === 'PASSED_GATE')?.id ?? null,
						p_value: label === 'CANDIDATE' ? 0.012 : 0.41,
						alpha: 0.05,
						rejected: label === 'CANDIDATE',
						rules_tested: rules.filter((r) => r.status === 'PASSED_GATE').length,
						replicates: 2000,
						mean_block_length: 9,
						seed: 123456
					},
					pbo: {
						value: 0.47,
						blocks: 16,
						combinations: 12870,
						rules: 3,
						noisy: true,
						caveat: 'Noisy at this sample length: treat PBO as a rough warning, not a measurement.'
					},
					pbo_unavailable: null
				},
		uncertainty: {
			research_bars: 800,
			sharpe_se_annualised_iid: 3.3,
			holdout_bars: 200,
			holdout_sharpe_se_annualised_iid: 6.6,
			note: 'Any sub-window is wider.'
		},
		integrity: {
			fill_model: 'next_open',
			signal_shift_verified: true,
			lookahead_probe: { passed: true, rules_checked: 16, truncation_bar: 600 },
			close_to_open_gap_bps: { mean_abs: 0.002, p99_abs: 0.02, max_abs: 0.32 },
			research_fingerprint: 'a1b2c3d4e5f60718'
		},
		notes: [
			'The legacy Research page fills at the signal close; this engine fills at the next open.'
		],
		...overrides
	};
}

export const freeze: VerdictFreeze = {
	id: 'f1',
	run_id: 'run-1',
	rule_ids: ['sma-5-20'],
	rules: [
		{ id: 'sma-5-20', name: 'SMA 5/20', family: 'SMA crossover', parameters: { fast: 5, slow: 20 } }
	],
	frozen_at: 1_790_100_000,
	forward_start: 1_790_000_000,
	hash: 'deadbeefcafe'
};

export const holdoutResult = (overrides: Partial<HoldoutResult> = {}): HoldoutResult => ({
	freeze_id: 'f1',
	read_at: 1_790_200_000,
	start: 1_789_900_000,
	end: 1_790_000_000,
	bars: 200,
	rules: [
		{
			id: 'sma-5-20',
			name: 'SMA 5/20',
			trades: 14,
			closed_trades: 13,
			exposure_pct: 49,
			net_return_pct: 1.2,
			sharpe: 0.9,
			sharpe_se: 6.6,
			mean_trade_return_pct: 0.1,
			buy_hold_return_pct: 0.6
		}
	],
	caveat:
		'With 200 holdout bars the annualised Sharpe standard error is about +/-6.6 even if the true Sharpe is zero. This is a sanity check, not a verdict.',
	sharpe_se_annualised_iid: 6.6,
	...overrides
});

export function verdictState(overrides: Partial<VerdictState> = {}): VerdictState {
	return {
		dataset: {
			id: 'abc',
			symbol: 'BINANCE:BTCUSDT',
			timeframe: '60',
			path: 'BINANCE_BTCUSDT/60.csv',
			rows: 1000
		},
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
			cost_notes: [
				{
					field: 'fee_bps_per_side',
					value: 10,
					basis: 'Binance spot taker, regular tier (VIP 0): 0.10% per side. Verify your own tier.'
				},
				{ field: 'spread_bps', value: 1, basis: 'Placeholder: captures contain no bid/ask data.' },
				{
					field: 'slippage_k',
					value: 0.1,
					basis: 'Starting value for liquid assets (0.05-0.2 x ATR(14)).'
				}
			],
			bootstrap_replicates: 2000,
			alpha: 0.05,
			dsr_threshold: 0.95,
			stress_multipliers: [1, 1.5, 2]
		},
		...overrides
	};
}
