import { describe, expect, it } from 'vitest';
import {
	filterRows,
	formatCell,
	formatFact,
	formatTimestamp,
	safeUrl,
	sentimentTone,
	sentimentWord,
	sortRows,
	toCsv
} from './format';
import { statusCopy } from './status';
import type { QueryStatus } from '$lib/api/providers';

describe('safeUrl', () => {
	it('allows http(s) only', () => {
		expect(safeUrl('https://example.test/a?b=1')).toBe('https://example.test/a?b=1');
		expect(safeUrl('http://example.test')).toBe('http://example.test');
		for (const bad of [
			'javascript:alert(1)',
			'data:text/html,x',
			'//example.test',
			'ftp://x',
			'',
			null,
			undefined,
			5
		]) {
			expect(safeUrl(bad)).toBeNull();
		}
	});
});

describe('formatFact / formatCell', () => {
	it('shows a dash for missing values, never zero', () => {
		expect(formatFact({ value: null, format: 'number' })).toBe('\u2014');
		expect(formatFact({ value: '', format: 'text' })).toBe('\u2014');
		expect(formatCell(null, 'number')).toBe('\u2014');
	});

	it('formats each kind of value', () => {
		expect(formatFact({ value: 3.456, format: 'percent' })).toBe('3.46%');
		expect(formatFact({ value: 3766484, format: 'integer' })).toBe('3,766,484');
		expect(formatFact({ value: 219.99, format: 'number' })).toBe('219.99');
		expect(formatFact({ value: 207_260_156_000, format: 'integer' })).toBe('207,260,156,000');
		expect(formatFact({ value: 0.4, format: 'sentiment' })).toBe('+0.40');
		expect(formatFact({ value: -0.25, format: 'sentiment' })).toBe('-0.25');
		expect(formatFact({ value: 'IBM', format: 'text' })).toBe('IBM');
		expect(formatFact({ value: 2_500_000_000_000, format: 'number' })).toBe('2.5T');
	});

	it('formats table cells by column type', () => {
		expect(formatCell(2.5, 'percent')).toBe('2.50%');
		expect(formatCell(1500, 'number')).toBe('1,500');
		expect(formatCell('2026-09-29', 'date')).toBe('2026-09-29');
	});
});

describe('sentiment helpers', () => {
	it('prefers the provider label and falls back to its documented score bands', () => {
		expect(sentimentWord(0.4, 'Somewhat-Bullish')).toBe('Somewhat Bullish');
		expect(sentimentWord(-0.4, null)).toBe('Bearish');
		expect(sentimentWord(-0.2, null)).toBe('Somewhat bearish');
		expect(sentimentWord(0, null)).toBe('Neutral');
		expect(sentimentWord(0.2, null)).toBe('Somewhat bullish');
		expect(sentimentWord(null, null)).toBe('\u2014');
	});
	it('colours only a clear lean', () => {
		expect(sentimentTone(0.5)).toBe('positive');
		expect(sentimentTone(-0.5)).toBe('negative');
		expect(sentimentTone(0.1)).toBeNull();
		expect(sentimentTone(null)).toBeNull();
	});
});

describe('formatTimestamp', () => {
	it('prints UTC and says so', () => {
		expect(formatTimestamp(1_790_000_000)).toBe('2026-09-21 14:13 UTC');
		expect(formatTimestamp(null)).toBe('\u2014');
	});
});

describe('table helpers', () => {
	const rows = [
		['b', 10],
		['a', null],
		['c', 2],
		['a', 7]
	];
	it('sorts numbers numerically, text naturally, missing values last in both directions, ties stably', () => {
		expect(sortRows(rows, 1, false).map((r) => r[1])).toEqual([2, 7, 10, null]);
		expect(sortRows(rows, 1, true).map((r) => r[1])).toEqual([10, 7, 2, null]);
		expect(sortRows(rows, 0, false).map((r) => `${r[0]}${r[1]}`)).toEqual([
			'anull',
			'a7',
			'b10',
			'c2'
		]);
		expect(sortRows([['x2'], ['x10'], ['x1']], 0, false)).toEqual([['x1'], ['x2'], ['x10']]);
	});
	it('does not modify its input', () => {
		const copy = JSON.stringify(rows);
		sortRows(rows, 1, true);
		expect(JSON.stringify(rows)).toBe(copy);
	});
	it('filters case-insensitively across every cell and ignores blank text', () => {
		expect(filterRows(rows, 'A')).toHaveLength(2);
		expect(filterRows(rows, '10')).toEqual([['b', 10]]);
		expect(filterRows(rows, '  ')).toBe(rows);
		expect(filterRows(rows, 'zzz')).toEqual([]);
	});
	it('writes quoted CSV and defuses spreadsheet formulas in text cells', () => {
		const csv = toCsv(
			[{ label: 'Name' }, { label: 'Note' }],
			[
				['=HYPERLINK("x")', 'He said "hi"'],
				[null, -5]
			]
		);
		expect(csv).toBe(
			['"Name","Note"', `"'=HYPERLINK(""x"")","He said ""hi"""`, '"","-5"'].join('\r\n')
		);
	});
});

describe('statusCopy', () => {
	const statuses: Exclude<QueryStatus, 'ok'>[] = [
		'premium_required',
		'rate_limited',
		'not_configured',
		'invalid_key',
		'invalid_request',
		'upstream_error',
		'empty'
	];
	it('has distinct words for every outcome that is not data', () => {
		const titles = statuses.map((s) => statusCopy(s, 'KEY_VAR').title);
		expect(new Set(titles).size).toBe(statuses.length);
	});
	it('names the key variable where it is the fix, and says sample data is not shown for premium', () => {
		expect(statusCopy('not_configured', 'MY_KEY').advice).toContain('MY_KEY');
		expect(statusCopy('invalid_key', 'MY_KEY').advice).toContain('MY_KEY');
		expect(statusCopy('premium_required', 'K')).toMatchObject({ tone: 'premium' });
		expect(statusCopy('premium_required', 'K').advice).toContain('not shown');
	});
});
