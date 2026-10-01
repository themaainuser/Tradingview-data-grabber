/** Display helpers for provider values. Missing values are an em dash, never zero. */
import { MISSING, formatValue } from '$lib/format';
import type { Cell, ColumnType, Fact, FactFormat } from '$lib/api/providers';

const SAFE_URL = /^https?:\/\//i;

/** A link target that is safe to put in an href: http(s) only. */
export const safeUrl = (value: unknown): string | null =>
	typeof value === 'string' && SAFE_URL.test(value) ? value : null;

function number(value: number): string {
	const magnitude = Math.abs(value);
	if (magnitude >= 1e12) return formatValue(value, 'compact');
	if (magnitude >= 1000 && Number.isInteger(value)) return value.toLocaleString('en-US');
	return formatValue(value, 'price');
}

export function formatFact(fact: Pick<Fact, 'value' | 'format'>): string {
	const { value, format } = fact;
	if (value === null || value === undefined || value === '') return MISSING;
	if (typeof value === 'string') return value;
	switch (format as FactFormat) {
		case 'percent':
			return `${value.toFixed(2)}%`;
		case 'integer':
			return value.toLocaleString('en-US');
		case 'currency':
			return `$${number(value)}`;
		case 'sentiment':
			return `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
		default:
			return number(value);
	}
}

export function formatCell(value: Cell, type: ColumnType): string {
	if (value === null || value === undefined || value === '') return MISSING;
	if (typeof value === 'string') return value;
	return type === 'percent' ? `${value.toFixed(2)}%` : number(value);
}

/** Sentiment scores run from -1 to +1; Alpha Vantage's own bands map them to a label. */
export function sentimentWord(score: number | null, label: string | null): string {
	if (label) return label.replace(/-/g, ' ');
	if (score === null) return MISSING;
	if (score <= -0.35) return 'Bearish';
	if (score <= -0.15) return 'Somewhat bearish';
	if (score < 0.15) return 'Neutral';
	if (score < 0.35) return 'Somewhat bullish';
	return 'Bullish';
}

export const sentimentTone = (score: number | null): 'positive' | 'negative' | null =>
	score === null || Math.abs(score) < 0.15 ? null : score > 0 ? 'positive' : 'negative';

export function formatTimestamp(seconds: number | null): string {
	if (seconds === null || !Number.isFinite(seconds)) return MISSING;
	return new Date(seconds * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

export function sortRows(rows: Cell[][], column: number, descending: boolean): Cell[][] {
	const direction = descending ? -1 : 1;
	return rows
		.map((row, index) => ({ row, index }))
		.sort((a, b) => {
			const x = a.row[column];
			const y = b.row[column];
			// Missing values sort last in either direction.
			if (x === null && y === null) return a.index - b.index;
			if (x === null) return 1;
			if (y === null) return -1;
			const order =
				typeof x === 'number' && typeof y === 'number'
					? x - y
					: String(x).localeCompare(String(y), 'en', { numeric: true });
			return order * direction || a.index - b.index;
		})
		.map((entry) => entry.row);
}

export function filterRows(rows: Cell[][], text: string): Cell[][] {
	const needle = text.trim().toLowerCase();
	if (!needle) return rows;
	return rows.filter((row) =>
		row.some((cell) => cell !== null && String(cell).toLowerCase().includes(needle))
	);
}

/** CSV text for the rows shown, quoting every cell and neutralising spreadsheet formulas. */
export function toCsv(columns: { label: string }[], rows: Cell[][]): string {
	const cell = (value: Cell) => {
		let text = value === null ? '' : String(value);
		if (/^[=+@\t\r-]/.test(text) && typeof value === 'string') text = `'${text}`;
		return `"${text.replace(/"/g, '""')}"`;
	};
	return [columns.map((c) => cell(c.label)), ...rows.map((r) => r.map(cell))]
		.map((r) => r.join(','))
		.join('\r\n');
}
