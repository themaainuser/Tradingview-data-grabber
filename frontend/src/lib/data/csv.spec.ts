import { describe, expect, it } from 'vitest';
import { CsvImportError, parseOhlcvCsv, parseTimestamp, splitCsvLine } from './csv';

const HEADER = 'index,time,open,high,low,close,volume';

describe('parseTimestamp', () => {
	it('understands epoch units, ISO and the legacy TradingView format', () => {
		expect(parseTimestamp('1784095680')).toBe(1784095680);
		expect(parseTimestamp('1784095680000')).toBe(1784095680);
		expect(parseTimestamp('2026-01-02 03:04:05')).toBe(Date.UTC(2026, 0, 2, 3, 4, 5) / 1000);
		expect(parseTimestamp('2026/01/02, 03:04:05')).toBe(Date.UTC(2026, 0, 2, 3, 4, 5) / 1000);
		expect(parseTimestamp('2026-01-02T03:04:05+05:30')).toBe(
			Date.UTC(2026, 0, 1, 21, 34, 5) / 1000
		);
		expect(parseTimestamp('Fri Jan 02 2026 08:34:05 GMT+0530 (India Standard Time)')).toBe(
			Date.UTC(2026, 0, 2, 3, 4, 5) / 1000
		);
	});

	it('returns NaN for garbage', () => {
		expect(parseTimestamp('')).toBeNaN();
		expect(parseTimestamp('yesterday')).toBeNaN();
	});
});

describe('splitCsvLine', () => {
	it('handles quoted delimiters and escaped quotes', () => {
		expect(splitCsvLine('a,"b,c","d ""e"""', ',')).toEqual(['a', 'b,c', 'd "e"']);
	});
});

describe('parseOhlcvCsv', () => {
	it('parses, sorts and de-duplicates keeping the last duplicate row', () => {
		const parsed = parseOhlcvCsv(
			[
				HEADER,
				'0,1700000120,12,13,11,12.5,100',
				'1,1700000000,10,11,9,10.5,50',
				'2,1700000060,10,12,10,11,60',
				'3,1700000060,10,12,10,11.5,70'
			].join('\n')
		);
		expect(Array.from(parsed.columns.time)).toEqual([1700000000, 1700000060, 1700000120]);
		expect(Array.from(parsed.columns.close)).toEqual([10.5, 11.5, 12.5]);
		expect(parsed.duplicateRows).toBe(1);
		expect(parsed.droppedRows).toBe(0);
	});

	it('drops and counts invalid rows using the backend rules', () => {
		const parsed = parseOhlcvCsv(
			[
				HEADER,
				'0,1700000000,10,11,9,10,5', // ok
				'1,1700000060,10,9,9,10,5', // high below close
				'2,1700000120,10,11,9,10,-1', // negative volume
				'3,1700000180,0,11,9,10,5', // zero price
				'4,1700000240,10,11,9,,5', // blank close
				'5,notatime,10,11,9,10,5', // bad time
				'6,1700000300,10,11,9,NaN,5' // non-finite
			].join('\n')
		);
		expect(parsed.length).toBe(1);
		expect(parsed.inputRows).toBe(7);
		expect(parsed.droppedRows).toBe(6);
	});

	it('accepts any column order, semicolons, BOM and CRLF', () => {
		const parsed = parseOhlcvCsv(
			'\uFEFFvolume;close;low;high;open;time\r\n5;10;9;11;10;1700000000\r\n'
		);
		expect(parsed.length).toBe(1);
		expect(parsed.columns.volume[0]).toBe(5);
	});

	it('rejects files that cannot produce data instead of inventing any', () => {
		expect(() => parseOhlcvCsv('')).toThrow(CsvImportError);
		expect(() => parseOhlcvCsv('time,open,close\n1,2,3')).toThrow(
			/Missing required column\(s\): high, low, volume/
		);
		expect(() => parseOhlcvCsv(`${HEADER}\n0,x,1,1,1,1,1`)).toThrow(/No valid OHLCV rows/);
	});
});
