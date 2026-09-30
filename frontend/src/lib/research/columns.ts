/**
 * Column model for the research table.
 *
 * Every metric the backend reports for a strategy (three sample windows x eleven statistics),
 * plus derived comparisons against buy-and-hold, walk-forward fold aggregates and the strategy
 * parameters, becomes a typed column. Columns feed both the grid and the shared filter engine,
 * so anything you can see you can filter and sort by.
 */
import type {
	MetricWindow,
	PerformanceMetrics,
	ResearchAsset,
	ResearchReport,
	ResearchResult
} from '$lib/api/contracts';
import type { NumberFormat } from '$lib/format';
import type { ColumnSource } from '$lib/filters/types';

export interface RowContext {
	benchmark: PerformanceMetrics | null;
}

export interface ResearchColumn {
	key: string;
	label: string;
	group: string;
	kind: 'numeric' | 'text';
	format: NumberFormat;
	description: string;
	/** Whether a larger number is better; drives colouring. null = neutral. */
	higherIsBetter: boolean | null;
	text?: (row: ResearchResult, ctx: RowContext) => string;
	number?: (row: ResearchResult, ctx: RowContext) => number;
}

type NumberFn = (row: ResearchResult, ctx: RowContext) => number;

const nan = (value: number | null | undefined): number =>
	typeof value === 'number' && Number.isFinite(value) ? value : NaN;

const METRICS: {
	key: keyof PerformanceMetrics;
	label: string;
	format: NumberFormat;
	better: boolean | null;
	description: string;
}[] = [
	{
		key: 'total_return_pct',
		label: 'Return',
		format: 'pct',
		better: true,
		description: 'Total compounded net return over the window.'
	},
	{
		key: 'cagr_pct',
		label: 'CAGR',
		format: 'pct',
		better: true,
		description: 'Annualised growth rate using the configured periods per year.'
	},
	{
		key: 'annualized_volatility_pct',
		label: 'Volatility',
		format: 'pct',
		better: false,
		description: 'Annualised standard deviation of net returns.'
	},
	{
		key: 'sharpe',
		label: 'Sharpe',
		format: 'ratio',
		better: true,
		description: 'Mean over standard deviation of returns, annualised, zero risk-free rate.'
	},
	{
		key: 'sortino',
		label: 'Sortino',
		format: 'ratio',
		better: true,
		description: 'Mean return over downside deviation, annualised.'
	},
	{
		key: 'max_drawdown_pct',
		label: 'Max drawdown',
		format: 'pct',
		better: true,
		description: 'Worst peak-to-trough loss (negative; closer to zero is better).'
	},
	{
		key: 'calmar',
		label: 'Calmar',
		format: 'ratio',
		better: true,
		description: 'CAGR divided by the absolute maximum drawdown.'
	},
	{
		key: 'trades',
		label: 'Trades',
		format: 'int',
		better: null,
		description: 'Completed round-trip trades in the window.'
	},
	{
		key: 'win_rate_pct',
		label: 'Win rate',
		format: 'pct',
		better: true,
		description: 'Share of trades with a positive net return.'
	},
	{
		key: 'exposure_pct',
		label: 'Exposure',
		format: 'pct',
		better: null,
		description: 'Share of bars holding a position.'
	},
	{ key: 'bars', label: 'Bars', format: 'int', better: null, description: 'Bars in the window.' }
];

const WINDOW_LABELS: Record<MetricWindow, string> = {
	full_sample: 'Full sample',
	in_sample: 'In-sample',
	forward: 'Forward'
};

const lastEquity = (curve: [string, number][]): number =>
	curve.length ? curve[curve.length - 1][1] : NaN;

function foldValues(row: ResearchResult, pick: (m: PerformanceMetrics) => number | null): number[] {
	return row.forward_folds.map((f) => nan(pick(f.metrics))).filter(Number.isFinite);
}

const mean = (values: number[]) =>
	values.length ? values.reduce((a, b) => a + b, 0) / values.length : NaN;
const lowest = (values: number[]) => (values.length ? Math.min(...values) : NaN);

function textColumn(
	key: string,
	label: string,
	description: string,
	text: (r: ResearchResult) => string
): ResearchColumn {
	return {
		key,
		label,
		group: 'Identity',
		kind: 'text',
		format: 'number',
		description,
		higherIsBetter: null,
		text
	};
}

function numberColumn(
	group: string,
	key: string,
	label: string,
	description: string,
	number: NumberFn,
	format: NumberFormat,
	higherIsBetter: boolean | null = true
): ResearchColumn {
	return { key, label, group, kind: 'numeric', format, description, higherIsBetter, number };
}

function staticColumns(): ResearchColumn[] {
	const columns: ResearchColumn[] = [
		textColumn('symbol', 'Market', 'Dataset the strategy was evaluated on.', (r) => r.symbol),
		textColumn('family', 'Family', 'Strategy family.', (r) => r.family),
		textColumn('name', 'Strategy', 'Strategy name with its parameters.', (r) => r.name)
	];
	for (const window of Object.keys(WINDOW_LABELS) as MetricWindow[]) {
		for (const m of METRICS) {
			columns.push(
				numberColumn(
					WINDOW_LABELS[window],
					`${window}.${m.key}`,
					m.label,
					`${m.description} (${WINDOW_LABELS[window].toLowerCase()})`,
					(r) => nan(r.metrics[window][m.key]),
					m.format,
					m.better
				)
			);
		}
	}
	const vs = 'Versus buy-and-hold';
	columns.push(
		numberColumn(
			vs,
			'rel.excess_return',
			'Excess return',
			'Full-sample return minus buy-and-hold return (percentage points).',
			(r, c) => nan(r.metrics.full_sample.total_return_pct) - nan(c.benchmark?.total_return_pct),
			'pct'
		),
		numberColumn(
			vs,
			'rel.sharpe_delta',
			'Sharpe vs benchmark',
			'Full-sample Sharpe minus buy-and-hold Sharpe.',
			(r, c) => nan(r.metrics.full_sample.sharpe) - nan(c.benchmark?.sharpe),
			'ratio'
		),
		numberColumn(
			vs,
			'rel.drawdown_gain',
			'Drawdown saved',
			'Full-sample max drawdown minus the benchmark drawdown; positive means shallower.',
			(r, c) => nan(r.metrics.full_sample.max_drawdown_pct) - nan(c.benchmark?.max_drawdown_pct),
			'pct'
		),
		numberColumn(
			vs,
			'rel.forward_vs_insample',
			'Fwd - in-sample Sharpe',
			'Forward Sharpe minus in-sample Sharpe. Large negatives suggest overfitting.',
			(r) => nan(r.metrics.forward.sharpe) - nan(r.metrics.in_sample.sharpe),
			'ratio'
		),
		numberColumn(
			vs,
			'rel.forward_retention',
			'Sharpe retention',
			'Forward Sharpe as a fraction of a positive in-sample Sharpe.',
			(r) => {
				const inSample = nan(r.metrics.in_sample.sharpe);
				return inSample > 0 ? nan(r.metrics.forward.sharpe) / inSample : NaN;
			},
			'ratio'
		)
	);
	const folds = 'Forward folds';
	columns.push(
		numberColumn(
			folds,
			'fold.count',
			'Folds',
			'Number of forward folds.',
			(r) => r.forward_folds.length,
			'int',
			null
		),
		numberColumn(
			folds,
			'fold.positive',
			'Positive folds',
			'Folds with a positive net return.',
			(r) => foldValues(r, (m) => m.total_return_pct).filter((v) => v > 0).length,
			'int'
		),
		numberColumn(
			folds,
			'fold.sharpe_mean',
			'Mean fold Sharpe',
			'Average Sharpe across forward folds.',
			(r) => mean(foldValues(r, (m) => m.sharpe)),
			'ratio'
		),
		numberColumn(
			folds,
			'fold.sharpe_min',
			'Worst fold Sharpe',
			'Lowest Sharpe across forward folds.',
			(r) => lowest(foldValues(r, (m) => m.sharpe)),
			'ratio'
		),
		numberColumn(
			folds,
			'fold.return_mean',
			'Mean fold return',
			'Average net return across forward folds.',
			(r) => mean(foldValues(r, (m) => m.total_return_pct)),
			'pct'
		),
		numberColumn(
			folds,
			'fold.return_min',
			'Worst fold return',
			'Lowest net return across forward folds.',
			(r) => lowest(foldValues(r, (m) => m.total_return_pct)),
			'pct'
		),
		numberColumn(
			folds,
			'fold.drawdown_worst',
			'Worst fold drawdown',
			'Deepest max drawdown across forward folds.',
			(r) => lowest(foldValues(r, (m) => m.max_drawdown_pct)),
			'pct'
		),
		numberColumn(
			'Equity curve',
			'curve.final_equity',
			'Final equity',
			'Growth of 1 unit over the full sample, net of costs.',
			(r) => lastEquity(r.equity_curve),
			'ratio'
		)
	);
	return columns;
}

/** Static columns plus one numeric column per parameter name found in the results. */
export function buildColumns(report: ResearchReport): ResearchColumn[] {
	const columns = staticColumns();
	const names = new Set<string>();
	for (const r of report.results) for (const key of Object.keys(r.parameters)) names.add(key);
	for (const name of [...names].sort()) {
		columns.push(
			numberColumn(
				'Parameters',
				`param.${name}`,
				name.charAt(0).toUpperCase() + name.slice(1),
				`Strategy parameter "${name}" (missing for families that do not use it).`,
				(r) => nan(r.parameters[name]),
				'number',
				null
			)
		);
	}
	return columns;
}

/** Columns shown by default; everything else is reachable from the column picker. */
export const DEFAULT_VISIBLE = [
	'symbol',
	'name',
	'forward.sharpe',
	'forward.total_return_pct',
	'forward.max_drawdown_pct',
	'forward.trades',
	'in_sample.sharpe',
	'full_sample.total_return_pct',
	'rel.excess_return',
	'fold.positive'
];

export interface ResearchTable {
	rows: readonly ResearchResult[];
	columns: readonly ResearchColumn[];
	column(key: string): ResearchColumn | undefined;
	source: ColumnSource;
	benchmarkFor(row: ResearchResult): PerformanceMetrics | null;
	/** Cell value for display: number, text or NaN. */
	cell(row: number, key: string): number | string;
}

/** Builds typed-array columns lazily: only fields a filter, sort or visible column touches are materialised. */
export function createResearchTable(report: ResearchReport): ResearchTable {
	const rows = report.results;
	const columns = buildColumns(report);
	const byKey = new Map(columns.map((c) => [c.key, c]));
	const assets = new Map<string, ResearchAsset>(report.assets.map((a) => [a.symbol, a]));
	const benchmarkFor = (row: ResearchResult) => assets.get(row.symbol)?.benchmark ?? null;
	const numeric = new Map<string, Float64Array>();
	const text = new Map<string, string[]>();

	const source: ColumnSource = {
		length: rows.length,
		ordered: false,
		numeric(field) {
			const column = byKey.get(field);
			if (!column || column.kind !== 'numeric' || !column.number) return null;
			let cached = numeric.get(field);
			if (!cached) {
				cached = new Float64Array(rows.length);
				for (let i = 0; i < rows.length; i++) {
					const v = column.number(rows[i], { benchmark: benchmarkFor(rows[i]) });
					cached[i] = Number.isFinite(v) ? v : NaN;
				}
				numeric.set(field, cached);
			}
			return cached;
		},
		text(field) {
			const column = byKey.get(field);
			if (!column || column.kind !== 'text' || !column.text) return null;
			let cached = text.get(field);
			if (!cached) {
				cached = rows.map((r) => column.text!(r, { benchmark: benchmarkFor(r) }));
				text.set(field, cached);
			}
			return cached;
		}
	};
	return {
		rows,
		columns,
		column: (key) => byKey.get(key),
		source,
		benchmarkFor,
		cell: (row, key) => source.numeric(key)?.[row] ?? source.text(key)?.[row] ?? NaN
	};
}

/**
 * Stable ordering of the rows selected by `mask`. Missing values always sort last, whatever the
 * direction, so a sparse column never buries real results.
 */
export function sortRows(
	table: ResearchTable,
	mask: Uint8Array | null,
	key: string,
	direction: 'asc' | 'desc'
): Uint32Array {
	const selected: number[] = [];
	for (let i = 0; i < table.rows.length; i++) if (!mask || mask[i] === 1) selected.push(i);
	const numbers = table.source.numeric(key);
	const texts = numbers ? null : table.source.text(key);
	const sign = direction === 'asc' ? 1 : -1;
	if (numbers) {
		selected.sort((a, b) => {
			const x = numbers[a];
			const y = numbers[b];
			const xMissing = x !== x;
			const yMissing = y !== y;
			if (xMissing || yMissing) return xMissing === yMissing ? a - b : xMissing ? 1 : -1;
			return x === y ? a - b : (x - y) * sign;
		});
	} else if (texts) {
		selected.sort((a, b) => texts[a].localeCompare(texts[b]) * sign || a - b);
	}
	return Uint32Array.from(selected);
}
