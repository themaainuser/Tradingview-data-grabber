/**
 * Wire types for the FastAPI backend (`tradingview_data/api.py`).
 *
 * These mirror the JSON exactly (snake_case, epoch-second timestamps, nulls for undefined
 * metrics). Client-side domain types live next to their consumers; `validate.ts` converts wire
 * payloads into them and rejects anything that breaks the contract.
 */

export interface DatasetSummary {
	/** Opaque, URL-safe id issued by `GET /api/datasets`. Never build one client-side. */
	id: string;
	symbol: string;
	/** Bar timeframe as TradingView spells it ("5", "60", "1D"); null for flat-layout files. */
	timeframe: string | null;
	/** Path relative to the backend data directory. */
	path: string;
	rows: number;
	size_bytes: number;
	/** ISO-8601 UTC. */
	modified: string;
	/** Epoch seconds of the first / last valid bar. */
	start: number | null;
	end: number | null;
	valid: boolean;
	error: string | null;
}

export interface DatasetListResponse {
	datasets: DatasetSummary[];
}

export interface DataQuality {
	source: string | null;
	input_rows: number;
	valid_rows: number;
	dropped_rows: number;
	duplicate_rows_collapsed: number;
	start: string;
	end: string;
	median_interval_seconds: number | null;
	gaps: { after: string; seconds: number }[];
}

export interface BarsColumnsWire {
	time: number[];
	open: (number | null)[];
	high: (number | null)[];
	low: (number | null)[];
	close: (number | null)[];
	volume: (number | null)[];
}

export interface BarsResponse {
	id: string;
	symbol: string;
	timeframe: string | null;
	rows: number;
	total_rows: number;
	dropped_rows: number;
	duplicate_rows_collapsed: number;
	columns: BarsColumnsWire;
	quality: DataQuality | null;
}

export interface HealthResponse {
	status: 'ok';
	data_dir: string;
	dataset_count: number;
}

export interface ResearchRequest {
	dataset_ids: string[];
	fee_bps: number;
	periods_per_year: number;
}

export interface PerformanceMetrics {
	bars: number;
	total_return_pct: number | null;
	cagr_pct: number | null;
	annualized_volatility_pct: number | null;
	sharpe: number | null;
	sortino: number | null;
	max_drawdown_pct: number | null;
	calmar: number | null;
	trades: number;
	win_rate_pct: number | null;
	exposure_pct: number | null;
}

export type MetricWindow = 'full_sample' | 'in_sample' | 'forward';

/** `[ISO timestamp, equity]` pairs, bounded to ~240 points by the backend. */
export type EquityCurve = [string, number][];

export interface ForwardFold {
	start: string;
	end: string;
	metrics: PerformanceMetrics;
}

export interface ResearchAsset {
	symbol: string;
	source: string;
	rows: number;
	start: string;
	end: string;
	quality: DataQuality;
	benchmark: PerformanceMetrics;
	benchmark_curve: EquityCurve;
}

export interface ResearchResult {
	id: string;
	symbol: string;
	source: string;
	family: string;
	name: string;
	parameters: Record<string, number>;
	metrics: Record<MetricWindow, PerformanceMetrics>;
	forward_folds: ForwardFold[];
	equity_curve: EquityCurve;
	benchmark_curve: EquityCurve;
}

export interface ModelNote {
	model: string;
	status: 'ok' | 'error';
	text: string;
}

export interface ResearchReport {
	schema_version: 1;
	metadata: {
		fee_bps_per_position_change: number;
		periods_per_year: number;
		strategy_count_per_asset: number;
		forward_validation: string;
		/** Present only when a dataset has a sealed holdout: the bars this run was not allowed to see. */
		sealed_holdouts?: { dataset_id: string; excluded_bars: number }[];
	};
	assets: ResearchAsset[];
	results: ResearchResult[];
	model_notes: ModelNote[];
	disclosures: string[];
}

// ---- Fear & Greed (GET /api/sentiment/fear-greed) -------------------------------------------

export type BandKey = 'extreme_fear' | 'fear' | 'neutral' | 'greed' | 'extreme_greed';

export interface FearGreedBand {
	key: BandKey;
	label: string;
	/** Inclusive lower bound on the 0-100 scale. */
	from: number;
	/** Exclusive upper bound, except the last band which includes 100. */
	to: number;
}

export interface FearGreedPoint {
	score: number;
	label: string;
	band: BandKey;
	/** UTC epoch seconds. */
	time: number;
}

export interface FearGreedSnapshots {
	yesterday: FearGreedPoint | null;
	week_ago: FearGreedPoint | null;
	month_ago: FearGreedPoint | null;
	year_high: FearGreedPoint;
	year_low: FearGreedPoint;
}

export interface FearGreedResponse {
	source: { name: string; index: string; url: string; endpoint: string; documented: boolean };
	/** UTC epoch seconds of the last successful upstream fetch. */
	fetched_at: number;
	/** True when a refresh failed and the last good data is being served. */
	stale: boolean;
	stale_reason: string | null;
	bands: FearGreedBand[];
	current: FearGreedPoint;
	snapshots: FearGreedSnapshots;
	points: {
		time: number[];
		score: number[];
		btc_price: (number | null)[];
		btc_volume: (number | null)[];
	};
	total_points: number;
}

// ---- Backend charts (GET /api/datasets/{id}/charts, GET /api/charts/correlation) -------------

export interface VolumeProfileChart {
	edges: number[];
	volume: number[];
	poc: number;
	value_low: number;
	value_high: number;
	total_volume: number;
}

export interface ReturnDistributionChart {
	edges: number[];
	counts: number[];
	normal: number[];
	outliers: { below: number; above: number };
	stats: {
		count: number;
		mean_pct: number;
		std_pct: number;
		skew: number | null;
		excess_kurtosis: number | null;
		min_pct: number;
		max_pct: number;
		positive_pct: number;
		var_95_pct: number;
		cvar_95_pct: number;
	};
}

export interface DrawdownChart {
	time: number[];
	drawdown_pct: number[];
	max_drawdown_pct: number;
	peak_time: number;
	trough_time: number;
	recovered_time: number | null;
	current_drawdown_pct: number;
	longest_underwater_bars: number;
}

export interface RollingVolatilityChart {
	window: number;
	time: number[];
	value_pct: (number | null)[];
}

export interface ActivityChart {
	/** UTC hours 0-23 (columns). */
	hours: number[];
	/** 0 = Monday ... 6 = Sunday (rows). */
	weekdays: number[];
	metrics: {
		volume: (number | null)[][];
		range_pct: (number | null)[][];
		return_pct: (number | null)[][];
	};
	counts: number[][];
}

export interface SeasonalityBucket {
	labels: string[];
	mean_return_pct: (number | null)[];
	hit_rate_pct: (number | null)[];
	count: number[];
}

export type ChartSection =
	| 'return_distribution'
	| 'drawdown'
	| 'rolling_volatility'
	| 'activity'
	| 'seasonality_weekday'
	| 'seasonality_hour';

export interface ChartsResponse {
	id: string;
	symbol: string;
	timeframe: string | null;
	bars: number;
	interval_seconds: number | null;
	intraday: boolean;
	volume_profile: VolumeProfileChart;
	return_distribution: ReturnDistributionChart | null;
	drawdown: DrawdownChart | null;
	rolling_volatility: RollingVolatilityChart | null;
	activity: ActivityChart | null;
	seasonality: { by_weekday: SeasonalityBucket | null; by_hour: SeasonalityBucket | null };
	/** Plain-English reason for every section that is null. */
	unavailable: Record<string, string>;
}

export interface CorrelationResponse {
	labels: string[];
	matrix: (number | null)[][];
	observations: number;
	start: number;
	end: number;
}

// ---- Verdict engine (POST /api/verdict/run and friends) ---------------------------------------

export type VerdictLabel = 'INSUFFICIENT_DATA' | 'INDISTINGUISHABLE_FROM_LUCK' | 'CANDIDATE';
export type RuleStatus = 'NEVER_TRADES' | 'INSUFFICIENT_TRADES' | 'PASSED_GATE' | 'ERROR';

export interface VerdictCosts {
	fee_bps_per_side: number;
	spread_bps: number;
	slippage_k: number;
}

export interface VerdictRequest {
	dataset_id: string;
	min_trades: number;
	costs: VerdictCosts;
	/** null lets the backend infer it from the bar spacing (continuous trading assumed). */
	periods_per_year: number | null;
}

export interface HoldoutInfo {
	fraction: number;
	/** UTC epoch seconds. */
	start: number;
	end: number;
	bars: number;
	sealed_at: number;
	status: 'unread' | 'read';
	read_at: number | null;
}

export interface VerdictStress {
	multiplier: number;
	sharpe: number | null;
	mean_trade_return_pct: number | null;
	total_return_pct: number | null;
}

export interface VerdictEvidence {
	sharpe: number | null;
	sharpe_se: number | null;
	mean_trade_return_pct: number | null;
	adjusted_p: number | null;
	dsr: number | null;
	dsr_sensitivity: {
		low_n: { n: number | null; dsr: number | null };
		high_n: { n: number | null; dsr: number | null };
	};
	break_even: {
		round_trip_bps: number | null;
		base_round_trip_bps: number | null;
		multiple: number | null;
	};
	stress: VerdictStress[];
	checks: { bootstrap: boolean; dsr: boolean; stress: boolean };
	candidate: boolean;
}

export interface VerdictRule {
	id: string;
	family: string;
	name: string;
	parameters: Record<string, number>;
	status: RuleStatus;
	trades: number;
	closed_trades: number;
	exposure_pct: number;
	error: string | null;
	/** null unless the rule passed the trade-count gate: gated rules get no Sharpe, p-value or DSR. */
	evidence: VerdictEvidence | null;
}

export interface VerdictLedgerSummary {
	trials_dataset: number;
	trials_total: number;
	runs_dataset: number;
	intact: boolean;
}

export interface VerdictStatistics {
	effective_n: {
		estimate: number;
		low: number;
		high: number;
		level: number;
		rules_used: number;
		ledger_trials: number;
		scaled_estimate: number;
	};
	reality_check: {
		statistic: string;
		best_rule: string | null;
		p_value: number | null;
		alpha: number;
		rejected: boolean;
		rules_tested: number;
		replicates: number;
		mean_block_length: number;
		seed: number;
	};
	pbo: {
		value: number | null;
		blocks: number;
		combinations: number;
		rules: number;
		noisy: boolean;
		caveat: string;
	} | null;
	pbo_unavailable: string | null;
}

export interface VerdictReport {
	run_id: string;
	created_at: number;
	dataset: { id: string; symbol: string; timeframe: string | null; path: string };
	verdict: { label: VerdictLabel; headline: string; reasons: string[] };
	settings: {
		min_trades: number;
		costs: VerdictCosts;
		periods_per_year: number;
		periods_per_year_inferred: boolean;
		alpha: number;
		dsr_threshold: number;
		stress_multipliers: number[];
		bootstrap: { replicates: number; mean_block_length: number; seed: number };
	};
	data: {
		bars_total: number;
		research_bars: number;
		research_start: number;
		research_end: number;
		forward_bars: number;
		holdout: HoldoutInfo & { created_now: boolean };
	};
	ledger: VerdictLedgerSummary;
	rules: VerdictRule[];
	statistics: VerdictStatistics | null;
	uncertainty: {
		research_bars: number;
		sharpe_se_annualised_iid: number | null;
		holdout_bars: number;
		holdout_sharpe_se_annualised_iid: number | null;
		note: string;
	};
	integrity: {
		fill_model: string;
		signal_shift_verified: boolean;
		lookahead_probe: { passed: boolean; rules_checked: number; truncation_bar: number };
		close_to_open_gap_bps: {
			mean_abs: number | null;
			p99_abs: number | null;
			max_abs: number | null;
		};
		research_fingerprint: string;
	};
	notes: string[];
}

export interface VerdictFreeze {
	id: string;
	run_id: string;
	rule_ids: string[];
	rules: { id: string; name: string; family: string; parameters: Record<string, number> }[];
	frozen_at: number;
	forward_start: number;
	hash: string;
}

export interface RuleWindow {
	id: string;
	name: string;
	trades: number;
	closed_trades: number;
	exposure_pct: number;
	net_return_pct: number | null;
	sharpe: number | null;
	sharpe_se: number | null;
	mean_trade_return_pct: number | null;
	buy_hold_return_pct: number | null;
}

export interface HoldoutResult {
	freeze_id: string;
	read_at: number;
	start: number;
	end: number;
	bars: number;
	rules: RuleWindow[];
	caveat: string;
	sharpe_se_annualised_iid: number | null;
}

export interface ForwardResult {
	freeze: VerdictFreeze;
	start: number;
	end: number | null;
	bars: number;
	waiting: boolean;
	rules: RuleWindow[];
	caveat: string;
	sharpe_se_annualised_iid: number | null;
}

export interface VerdictDefaults {
	min_trades: number;
	holdout_fraction: number;
	costs: VerdictCosts;
	cost_notes: { field: string; value: number; basis: string }[];
	bootstrap_replicates: number;
	alpha: number;
	dsr_threshold: number;
	stress_multipliers: number[];
}

export interface VerdictState {
	dataset: { id: string; symbol: string; timeframe: string | null; path: string; rows: number };
	sealed: boolean;
	holdout: HoldoutInfo | null;
	ledger: VerdictLedgerSummary;
	latest: VerdictReport | null;
	freeze: VerdictFreeze | null;
	holdout_read: HoldoutResult | null;
	defaults: VerdictDefaults;
}

export interface LedgerView {
	intact: boolean;
	total_entries: number;
	trials: {
		dataset: number;
		total: number;
		keys: { key: string; rule_id: string; first_seen: number; runs: number }[];
	};
	entries: { seq: number; type: string; at: string; hash: string; prev: string; summary: string }[];
}
