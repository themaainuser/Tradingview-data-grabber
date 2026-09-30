/**
 * Runtime validation of backend payloads.
 *
 * TypeScript types vanish at runtime, so every response is checked here before it reaches a
 * store. A payload that violates the contract raises ApiError('contract') instead of silently
 * rendering wrong numbers: a mismatched column length or unsorted time axis would otherwise
 * corrupt every indicator downstream.
 */
import type { OhlcvColumns } from '$lib/indicators/types';
import { ApiError } from './errors';
import type {
	BandKey,
	ChartsResponse,
	CorrelationResponse,
	DataQuality,
	DatasetListResponse,
	DatasetSummary,
	FearGreedBand,
	FearGreedPoint,
	FearGreedResponse,
	ResearchReport,
	SeasonalityBucket
} from './contracts';

/** Bars ready for compute: typed columns plus provenance. */
export interface Bars {
	id: string;
	symbol: string;
	timeframe: string | null;
	columns: OhlcvColumns;
	length: number;
	totalRows: number;
	droppedRows: number;
	duplicateRows: number;
	quality: DataQuality | null;
	origin: 'backend' | 'local';
}

type Obj = Record<string, unknown>;

export function fail(path: string, expected: string): never {
	throw new ApiError('contract', `Unexpected response: ${path} should be ${expected}`);
}

export function obj(value: unknown, path: string): Obj {
	if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(path, 'an object');
	return value as Obj;
}

export function arr(value: unknown, path: string): unknown[] {
	if (!Array.isArray(value)) fail(path, 'an array');
	return value as unknown[];
}

export function str(value: unknown, path: string): string {
	if (typeof value !== 'string') fail(path, 'a string');
	return value as string;
}

export function num(value: unknown, path: string): number {
	if (typeof value !== 'number' || !Number.isFinite(value)) fail(path, 'a finite number');
	return value as number;
}

export function nullableNum(value: unknown, path: string): number | null {
	return value === null || value === undefined ? null : num(value, path);
}

export function nullableStr(value: unknown, path: string): string | null {
	return value === null || value === undefined ? null : str(value, path);
}

export function parseDatasetList(json: unknown): DatasetListResponse {
	const items = arr(obj(json, 'response').datasets, 'datasets');
	const datasets = items.map((raw, i): DatasetSummary => {
		const p = `datasets[${i}]`;
		const o = obj(raw, p);
		return {
			id: str(o.id, `${p}.id`),
			symbol: str(o.symbol, `${p}.symbol`),
			timeframe: nullableStr(o.timeframe, `${p}.timeframe`),
			path: str(o.path, `${p}.path`),
			rows: num(o.rows, `${p}.rows`),
			size_bytes: num(o.size_bytes, `${p}.size_bytes`),
			modified: str(o.modified, `${p}.modified`),
			start: nullableNum(o.start, `${p}.start`),
			end: nullableNum(o.end, `${p}.end`),
			valid: o.valid === true,
			error: nullableStr(o.error, `${p}.error`)
		};
	});
	return { datasets };
}

const PRICE_COLUMNS = ['open', 'high', 'low', 'close', 'volume'] as const;

/** Converts a column, mapping JSON null (the only way to encode "missing") to NaN. */
function floatColumn(value: unknown, path: string, length: number): Float64Array {
	const values = arr(value, path);
	if (values.length !== length) fail(path, `an array of ${length} values (got ${values.length})`);
	const out = new Float64Array(length);
	for (let i = 0; i < length; i++) {
		const v = values[i];
		if (v === null) out[i] = NaN;
		else if (typeof v === 'number' && Number.isFinite(v)) out[i] = v;
		else fail(`${path}[${i}]`, 'a finite number or null');
	}
	return out;
}

/** Validates a columnar bars payload and returns typed arrays with a strictly increasing time axis. */
export function parseBars(json: unknown): Bars {
	const o = obj(json, 'response');
	const wire = obj(o.columns, 'columns');
	const time = arr(wire.time, 'columns.time');
	const length = time.length;
	const timeColumn = new Float64Array(length);
	for (let i = 0; i < length; i++) {
		const t = time[i];
		if (typeof t !== 'number' || !Number.isFinite(t)) fail(`columns.time[${i}]`, 'a finite number');
		if (i > 0 && (t as number) <= timeColumn[i - 1]) {
			fail(`columns.time[${i}]`, 'strictly increasing');
		}
		timeColumn[i] = t as number;
	}
	const columns = { time: timeColumn } as OhlcvColumns;
	for (const name of PRICE_COLUMNS) {
		columns[name] = floatColumn(wire[name], `columns.${name}`, length);
	}
	return {
		id: str(o.id, 'id'),
		symbol: str(o.symbol, 'symbol'),
		timeframe: nullableStr(o.timeframe, 'timeframe'),
		columns,
		length,
		totalRows: num(o.total_rows ?? length, 'total_rows'),
		droppedRows: num(o.dropped_rows ?? 0, 'dropped_rows'),
		duplicateRows: num(o.duplicate_rows_collapsed ?? 0, 'duplicate_rows_collapsed'),
		quality: o.quality == null ? null : (obj(o.quality, 'quality') as unknown as DataQuality),
		origin: 'backend'
	};
}

const WINDOWS = ['full_sample', 'in_sample', 'forward'] as const;

function checkMetrics(value: unknown, path: string): void {
	const metrics = obj(value, path);
	num(metrics.bars, `${path}.bars`);
	num(metrics.trades, `${path}.trades`);
	for (const [key, v] of Object.entries(metrics)) nullableNum(v, `${path}.${key}`);
}

function checkCurve(value: unknown, path: string): void {
	for (const [i, point] of arr(value, path).entries()) {
		const pair = arr(point, `${path}[${i}]`);
		str(pair[0], `${path}[${i}][0]`);
		num(pair[1], `${path}[${i}][1]`);
	}
}

/**
 * Validates a research report. Nested metric objects keep the backend's null-for-undefined
 * convention; the research table maps null to NaN when it builds typed columns.
 */
export function parseResearch(json: unknown): ResearchReport {
	const o = obj(json, 'response');
	if (o.schema_version !== 1) fail('schema_version', '1 (unsupported research schema)');
	const metadata = obj(o.metadata, 'metadata');
	if (metadata.sealed_holdouts !== undefined) {
		for (const [i, raw] of arr(metadata.sealed_holdouts, 'metadata.sealed_holdouts').entries()) {
			const sealed = obj(raw, `metadata.sealed_holdouts[${i}]`);
			str(sealed.dataset_id, `metadata.sealed_holdouts[${i}].dataset_id`);
			num(sealed.excluded_bars, `metadata.sealed_holdouts[${i}].excluded_bars`);
		}
	}
	const assets = arr(o.assets, 'assets');
	for (const [i, a] of assets.entries()) {
		const asset = obj(a, `assets[${i}]`);
		str(asset.symbol, `assets[${i}].symbol`);
		checkMetrics(asset.benchmark, `assets[${i}].benchmark`);
		checkCurve(asset.benchmark_curve, `assets[${i}].benchmark_curve`);
	}
	const results = arr(o.results, 'results');
	const ids = new Set<string>();
	for (const [i, r] of results.entries()) {
		const p = `results[${i}]`;
		const result = obj(r, p);
		const id = str(result.id, `${p}.id`);
		if (ids.has(id)) fail(`${p}.id`, `unique (duplicate "${id}")`);
		ids.add(id);
		str(result.symbol, `${p}.symbol`);
		str(result.family, `${p}.family`);
		str(result.name, `${p}.name`);
		for (const [key, v] of Object.entries(obj(result.parameters, `${p}.parameters`))) {
			num(v, `${p}.parameters.${key}`);
		}
		const metrics = obj(result.metrics, `${p}.metrics`);
		for (const window of WINDOWS) checkMetrics(metrics[window], `${p}.metrics.${window}`);
		for (const [j, fold] of arr(result.forward_folds, `${p}.forward_folds`).entries()) {
			checkMetrics(
				obj(fold, `${p}.forward_folds[${j}]`).metrics,
				`${p}.forward_folds[${j}].metrics`
			);
		}
		checkCurve(result.equity_curve, `${p}.equity_curve`);
		checkCurve(result.benchmark_curve, `${p}.benchmark_curve`);
	}
	arr(o.disclosures, 'disclosures');
	if (o.model_notes !== undefined) arr(o.model_notes, 'model_notes');
	const report = o as unknown as ResearchReport;
	report.model_notes ??= [];
	return report;
}

// ---- Fear & Greed ----------------------------------------------------------------------------

const BAND_KEYS: readonly BandKey[] = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'];

export function bool(value: unknown, path: string): boolean {
	if (typeof value !== 'boolean') fail(path, 'a boolean');
	return value as boolean;
}

function score(value: unknown, path: string): number {
	const n = num(value, path);
	if (!Number.isInteger(n) || n < 0 || n > 100) fail(path, 'a whole number from 0 to 100');
	return n;
}

function bandKey(value: unknown, path: string): BandKey {
	const key = str(value, path);
	if (!BAND_KEYS.includes(key as BandKey)) fail(path, `one of ${BAND_KEYS.join(', ')}`);
	return key as BandKey;
}

function fearGreedPoint(value: unknown, path: string): FearGreedPoint {
	const o = obj(value, path);
	return {
		score: score(o.score, `${path}.score`),
		label: str(o.label, `${path}.label`),
		band: bandKey(o.band, `${path}.band`),
		time: num(o.time, `${path}.time`)
	};
}

function optionalPoint(value: unknown, path: string): FearGreedPoint | null {
	return value === null || value === undefined ? null : fearGreedPoint(value, path);
}

/** Validates the Fear & Greed payload: columns equal length, time ascending, scores on the 0-100 scale. */
export function parseFearGreed(json: unknown): FearGreedResponse {
	const o = obj(json, 'response');
	const source = obj(o.source, 'source');
	const bands = arr(o.bands, 'bands').map((raw, i): FearGreedBand => {
		const b = obj(raw, `bands[${i}]`);
		return {
			key: bandKey(b.key, `bands[${i}].key`),
			label: str(b.label, `bands[${i}].label`),
			from: num(b.from, `bands[${i}].from`),
			to: num(b.to, `bands[${i}].to`)
		};
	});
	if (bands.length === 0) fail('bands', 'a non-empty array');

	const points = obj(o.points, 'points');
	const time = arr(points.time, 'points.time');
	const length = time.length;
	if (length === 0) fail('points.time', 'a non-empty array');
	const timeColumn = time.map((t, i) => {
		const n = num(t, `points.time[${i}]`);
		if (i > 0 && n <= (time[i - 1] as number)) fail(`points.time[${i}]`, 'strictly increasing');
		return n;
	});
	const scores = arr(points.score, 'points.score');
	if (scores.length !== length) fail('points.score', `an array of ${length} values`);
	const column = (name: 'btc_price' | 'btc_volume'): (number | null)[] => {
		const values = arr(points[name], `points.${name}`);
		if (values.length !== length) fail(`points.${name}`, `an array of ${length} values`);
		return values.map((v, i) => nullableNum(v, `points.${name}[${i}]`));
	};

	const snapshots = obj(o.snapshots, 'snapshots');
	return {
		source: {
			name: str(source.name, 'source.name'),
			index: str(source.index, 'source.index'),
			url: str(source.url, 'source.url'),
			endpoint: str(source.endpoint, 'source.endpoint'),
			documented: bool(source.documented, 'source.documented')
		},
		fetched_at: num(o.fetched_at, 'fetched_at'),
		stale: bool(o.stale, 'stale'),
		stale_reason: nullableStr(o.stale_reason, 'stale_reason'),
		bands,
		current: fearGreedPoint(o.current, 'current'),
		snapshots: {
			yesterday: optionalPoint(snapshots.yesterday, 'snapshots.yesterday'),
			week_ago: optionalPoint(snapshots.week_ago, 'snapshots.week_ago'),
			month_ago: optionalPoint(snapshots.month_ago, 'snapshots.month_ago'),
			year_high: fearGreedPoint(snapshots.year_high, 'snapshots.year_high'),
			year_low: fearGreedPoint(snapshots.year_low, 'snapshots.year_low')
		},
		points: {
			time: timeColumn,
			score: scores.map((v, i) => score(v, `points.score[${i}]`)),
			btc_price: column('btc_price'),
			btc_volume: column('btc_volume')
		},
		total_points: num(o.total_points, 'total_points')
	};
}

// ---- Backend charts --------------------------------------------------------------------------

export function numbers(value: unknown, path: string, length?: number): number[] {
	const values = arr(value, path);
	if (length !== undefined && values.length !== length) fail(path, `an array of ${length} values`);
	return values.map((v, i) => num(v, `${path}[${i}]`));
}

function nullableNumbers(value: unknown, path: string, length?: number): (number | null)[] {
	const values = arr(value, path);
	if (length !== undefined && values.length !== length) fail(path, `an array of ${length} values`);
	return values.map((v, i) => nullableNum(v, `${path}[${i}]`));
}

function grid(value: unknown, path: string, rows: number, cols: number): (number | null)[][] {
	const r = arr(value, path);
	if (r.length !== rows) fail(path, `${rows} rows`);
	return r.map((row, i) => nullableNumbers(row, `${path}[${i}]`, cols));
}

function seasonality(value: unknown, path: string, buckets: number): SeasonalityBucket | null {
	if (value === null || value === undefined) return null;
	const o = obj(value, path);
	const labels = arr(o.labels, `${path}.labels`).map((l, i) => str(l, `${path}.labels[${i}]`));
	if (labels.length !== buckets) fail(`${path}.labels`, `${buckets} labels`);
	return {
		labels,
		mean_return_pct: nullableNumbers(o.mean_return_pct, `${path}.mean_return_pct`, buckets),
		hit_rate_pct: nullableNumbers(o.hit_rate_pct, `${path}.hit_rate_pct`, buckets),
		count: numbers(o.count, `${path}.count`, buckets)
	};
}

function parseVolumeProfile(value: unknown): ChartsResponse['volume_profile'] {
	const vp = obj(value, 'volume_profile');
	const volume = numbers(vp.volume, 'volume_profile.volume');
	return {
		edges: numbers(vp.edges, 'volume_profile.edges', volume.length + 1),
		volume,
		poc: num(vp.poc, 'volume_profile.poc'),
		value_low: num(vp.value_low, 'volume_profile.value_low'),
		value_high: num(vp.value_high, 'volume_profile.value_high'),
		total_volume: num(vp.total_volume, 'volume_profile.total_volume')
	};
}

function parseReturnDistribution(
	value: unknown
): NonNullable<ChartsResponse['return_distribution']> {
	const d = obj(value, 'return_distribution');
	const counts = numbers(d.counts, 'return_distribution.counts');
	const stats = obj(d.stats, 'return_distribution.stats');
	const outliers = obj(d.outliers, 'return_distribution.outliers');
	const s = (k: string) => num(stats[k], `return_distribution.stats.${k}`);
	return {
		edges: numbers(d.edges, 'return_distribution.edges', counts.length + 1),
		counts,
		normal: numbers(d.normal, 'return_distribution.normal', counts.length),
		outliers: {
			below: num(outliers.below, 'return_distribution.outliers.below'),
			above: num(outliers.above, 'return_distribution.outliers.above')
		},
		stats: {
			count: s('count'),
			mean_pct: s('mean_pct'),
			std_pct: s('std_pct'),
			skew: nullableNum(stats.skew, 'return_distribution.stats.skew'),
			excess_kurtosis: nullableNum(
				stats.excess_kurtosis,
				'return_distribution.stats.excess_kurtosis'
			),
			min_pct: s('min_pct'),
			max_pct: s('max_pct'),
			positive_pct: s('positive_pct'),
			var_95_pct: s('var_95_pct'),
			cvar_95_pct: s('cvar_95_pct')
		}
	};
}

function parseDrawdown(value: unknown): NonNullable<ChartsResponse['drawdown']> {
	const d = obj(value, 'drawdown');
	const time = numbers(d.time, 'drawdown.time');
	return {
		time,
		drawdown_pct: numbers(d.drawdown_pct, 'drawdown.drawdown_pct', time.length),
		max_drawdown_pct: num(d.max_drawdown_pct, 'drawdown.max_drawdown_pct'),
		peak_time: num(d.peak_time, 'drawdown.peak_time'),
		trough_time: num(d.trough_time, 'drawdown.trough_time'),
		recovered_time: nullableNum(d.recovered_time, 'drawdown.recovered_time'),
		current_drawdown_pct: num(d.current_drawdown_pct, 'drawdown.current_drawdown_pct'),
		longest_underwater_bars: num(d.longest_underwater_bars, 'drawdown.longest_underwater_bars')
	};
}

function parseActivity(value: unknown): NonNullable<ChartsResponse['activity']> {
	const d = obj(value, 'activity');
	const hours = numbers(d.hours, 'activity.hours');
	const weekdays = numbers(d.weekdays, 'activity.weekdays');
	const metrics = obj(d.metrics, 'activity.metrics');
	const g = (name: 'volume' | 'range_pct' | 'return_pct') =>
		grid(metrics[name], `activity.metrics.${name}`, weekdays.length, hours.length);
	return {
		hours,
		weekdays,
		metrics: { volume: g('volume'), range_pct: g('range_pct'), return_pct: g('return_pct') },
		counts: grid(d.counts, 'activity.counts', weekdays.length, hours.length) as number[][]
	};
}

/** Validates the chart-data payload. Sections the backend could not compute arrive as null with a reason. */
export function parseCharts(json: unknown): ChartsResponse {
	const o = obj(json, 'response');
	const season = obj(o.seasonality ?? {}, 'seasonality');
	const unavailable: Record<string, string> = {};
	for (const [key, reason] of Object.entries(obj(o.unavailable ?? {}, 'unavailable'))) {
		unavailable[key] = str(reason, `unavailable.${key}`);
	}
	let rollingVolatility: ChartsResponse['rolling_volatility'] = null;
	if (o.rolling_volatility != null) {
		const d = obj(o.rolling_volatility, 'rolling_volatility');
		const time = numbers(d.time, 'rolling_volatility.time');
		rollingVolatility = {
			window: num(d.window, 'rolling_volatility.window'),
			time,
			value_pct: nullableNumbers(d.value_pct, 'rolling_volatility.value_pct', time.length)
		};
	}
	return {
		id: str(o.id, 'id'),
		symbol: str(o.symbol, 'symbol'),
		timeframe: nullableStr(o.timeframe, 'timeframe'),
		bars: num(o.bars, 'bars'),
		interval_seconds: nullableNum(o.interval_seconds, 'interval_seconds'),
		intraday: bool(o.intraday, 'intraday'),
		volume_profile: parseVolumeProfile(o.volume_profile),
		return_distribution:
			o.return_distribution == null ? null : parseReturnDistribution(o.return_distribution),
		drawdown: o.drawdown == null ? null : parseDrawdown(o.drawdown),
		rolling_volatility: rollingVolatility,
		activity: o.activity == null ? null : parseActivity(o.activity),
		seasonality: {
			by_weekday: seasonality(season.by_weekday, 'seasonality.by_weekday', 7),
			by_hour: seasonality(season.by_hour, 'seasonality.by_hour', 24)
		},
		unavailable
	};
}

/** Validates a correlation matrix: square, label-aligned, values within [-1, 1] or null. */
export function parseCorrelation(json: unknown): CorrelationResponse {
	const o = obj(json, 'response');
	const labels = arr(o.labels, 'labels').map((l, i) => str(l, `labels[${i}]`));
	if (labels.length < 2) fail('labels', 'at least two labels');
	const matrix = grid(o.matrix, 'matrix', labels.length, labels.length);
	for (const [i, row] of matrix.entries()) {
		for (const [j, value] of row.entries()) {
			if (value !== null && Math.abs(value) > 1 + 1e-9)
				fail(`matrix[${i}][${j}]`, 'between -1 and 1');
		}
	}
	return {
		labels,
		matrix,
		observations: num(o.observations, 'observations'),
		start: num(o.start, 'start'),
		end: num(o.end, 'end')
	};
}
