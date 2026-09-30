/**
 * Client-side OHLCV CSV import: the "user action" source of data.
 *
 * Applies the same validation rules as the backend loader (`analytics.load_ohlcv`): rows with
 * missing/non-finite values, non-positive prices, negative volume or inconsistent high/low are
 * dropped and counted, duplicate timestamps keep the last row, and rows are sorted by time.
 * Nothing is invented: a file that yields no valid row is rejected with a reason.
 */
import type { Bars } from '$lib/api/validate';
import type { OhlcvColumns } from '$lib/indicators/types';

export class CsvImportError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'CsvImportError';
	}
}

export const MAX_IMPORT_BYTES = 100 * 1024 * 1024;

const REQUIRED = ['time', 'open', 'high', 'low', 'close', 'volume'] as const;

/** Splits one CSV line, honouring double-quoted fields. */
export function splitCsvLine(line: string, delimiter: string): string[] {
	const fields: string[] = [];
	let current = '';
	let quoted = false;
	for (let i = 0; i < line.length; i++) {
		const ch = line[i];
		if (quoted) {
			if (ch === '"' && line[i + 1] === '"') {
				current += '"';
				i++;
			} else if (ch === '"') quoted = false;
			else current += ch;
		} else if (ch === '"') quoted = true;
		else if (ch === delimiter) {
			fields.push(current);
			current = '';
		} else current += ch;
	}
	fields.push(current);
	return fields;
}

const EPOCH_DIGITS: Record<number, number> = { 10: 1, 13: 1e-3, 16: 1e-6, 19: 1e-9 };

/**
 * Parses a timestamp to epoch seconds, or NaN. Mirrors the backend's accepted forms; strings
 * with no timezone are read as UTC (the backend assumes Asia/Kolkata; only the axis labels differ).
 */
export function parseTimestamp(raw: string): number {
	let text = raw.trim();
	if (!text) return NaN;
	if (text.endsWith(')') && text.includes(' (')) text = text.slice(0, text.lastIndexOf(' ('));
	const digits = text.replace(/^[+-]/, '');
	if (/^\d+$/.test(digits) && EPOCH_DIGITS[digits.length]) {
		return Number(text) * EPOCH_DIGITS[digits.length];
	}
	const slashed = /^(\d{4})\/(\d{2})\/(\d{2}),?\s+(\d{2}:\d{2}:\d{2})$/.exec(text);
	if (slashed) text = `${slashed[1]}-${slashed[2]}-${slashed[3]}T${slashed[4]}Z`;
	else if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text)) {
		text = `${text.replace(' ', 'T')}Z`;
	} else if (/^\d{4}-\d{2}-\d{2}$/.test(text)) text = `${text}T00:00:00Z`;
	const ms = Date.parse(text);
	return Number.isFinite(ms) ? ms / 1000 : NaN;
}

function detectDelimiter(header: string): string {
	const counts = [',', ';', '\t'].map((d) => [d, header.split(d).length] as const);
	return counts.sort((a, b) => b[1] - a[1])[0][0];
}

export interface ParsedCsv {
	columns: OhlcvColumns;
	length: number;
	inputRows: number;
	droppedRows: number;
	duplicateRows: number;
}

export function parseOhlcvCsv(text: string): ParsedCsv {
	const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
	const headerIndex = lines.findIndex((l) => l.trim() !== '');
	if (headerIndex < 0) throw new CsvImportError('The file is empty.');
	const delimiter = detectDelimiter(lines[headerIndex]);
	const header = splitCsvLine(lines[headerIndex], delimiter).map((h) => h.trim().toLowerCase());
	const position = Object.fromEntries(REQUIRED.map((name) => [name, header.indexOf(name)]));
	const missing = REQUIRED.filter((name) => position[name] < 0);
	if (missing.length) {
		throw new CsvImportError(
			`Missing required column(s): ${missing.join(', ')}. Expected ${REQUIRED.join(', ')}.`
		);
	}

	const rows: number[][] = [];
	let inputRows = 0;
	let dropped = 0;
	for (let i = headerIndex + 1; i < lines.length; i++) {
		if (lines[i].trim() === '') continue;
		inputRows++;
		const cells = splitCsvLine(lines[i], delimiter);
		const t = parseTimestamp(cells[position.time] ?? '');
		const o = Number(cells[position.open]);
		const h = Number(cells[position.high]);
		const l = Number(cells[position.low]);
		const c = Number(cells[position.close]);
		const v = Number(cells[position.volume]);
		const finite = [t, o, h, l, c, v].every(Number.isFinite);
		// Number('') is 0, which would pass as a price: reject blank cells explicitly.
		const blank = [
			position.open,
			position.high,
			position.low,
			position.close,
			position.volume
		].some((p) => (cells[p] ?? '').trim() === '');
		const sane =
			finite &&
			!blank &&
			o > 0 &&
			h > 0 &&
			l > 0 &&
			c > 0 &&
			v >= 0 &&
			h >= Math.max(o, c, l) &&
			l <= Math.min(o, c, h);
		if (sane) rows.push([t, o, h, l, c, v]);
		else dropped++;
	}
	if (rows.length === 0) {
		throw new CsvImportError(
			`No valid OHLCV rows found (${inputRows} row${inputRows === 1 ? '' : 's'} rejected).`
		);
	}

	// Stable sort keeps file order among equal timestamps so "keep last" matches the backend.
	rows.sort((a, b) => a[0] - b[0]);
	const kept: number[][] = [];
	for (const row of rows) {
		if (kept.length && kept[kept.length - 1][0] === row[0]) kept[kept.length - 1] = row;
		else kept.push(row);
	}
	const length = kept.length;
	const columns: OhlcvColumns = {
		time: new Float64Array(length),
		open: new Float64Array(length),
		high: new Float64Array(length),
		low: new Float64Array(length),
		close: new Float64Array(length),
		volume: new Float64Array(length)
	};
	for (let i = 0; i < length; i++) {
		const [t, o, h, l, c, v] = kept[i];
		columns.time[i] = t;
		columns.open[i] = o;
		columns.high[i] = h;
		columns.low[i] = l;
		columns.close[i] = c;
		columns.volume[i] = v;
	}
	return { columns, length, inputRows, droppedRows: dropped, duplicateRows: rows.length - length };
}

let localSequence = 0;

/** Reads a user-selected file into Bars. Symbol/timeframe come from the file name only. */
export async function importCsvFile(file: File): Promise<Bars> {
	if (file.size > MAX_IMPORT_BYTES) {
		throw new CsvImportError(`${file.name} is larger than ${MAX_IMPORT_BYTES / 1024 / 1024} MB.`);
	}
	const parsed = parseOhlcvCsv(await file.text());
	localSequence += 1;
	return {
		id: `local:${localSequence}`,
		symbol: file.name.replace(/\.[^.]+$/, ''),
		timeframe: null,
		columns: parsed.columns,
		length: parsed.length,
		totalRows: parsed.length,
		droppedRows: parsed.droppedRows,
		duplicateRows: parsed.duplicateRows,
		quality: null,
		origin: 'local'
	};
}
