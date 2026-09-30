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
	};
	assets: ResearchAsset[];
	results: ResearchResult[];
	model_notes: ModelNote[];
	disclosures: string[];
}
