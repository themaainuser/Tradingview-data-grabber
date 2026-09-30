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
import type { DataQuality, DatasetListResponse, DatasetSummary, ResearchReport } from './contracts';

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

function fail(path: string, expected: string): never {
	throw new ApiError('contract', `Unexpected response: ${path} should be ${expected}`);
}

function obj(value: unknown, path: string): Obj {
	if (typeof value !== 'object' || value === null || Array.isArray(value)) fail(path, 'an object');
	return value as Obj;
}

function arr(value: unknown, path: string): unknown[] {
	if (!Array.isArray(value)) fail(path, 'an array');
	return value as unknown[];
}

function str(value: unknown, path: string): string {
	if (typeof value !== 'string') fail(path, 'a string');
	return value as string;
}

function num(value: unknown, path: string): number {
	if (typeof value !== 'number' || !Number.isFinite(value)) fail(path, 'a finite number');
	return value as number;
}

function nullableNum(value: unknown, path: string): number | null {
	return value === null || value === undefined ? null : num(value, path);
}

function nullableStr(value: unknown, path: string): string | null {
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
	obj(o.metadata, 'metadata');
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
