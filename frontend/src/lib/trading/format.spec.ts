import { describe, expect, it } from 'vitest';
import {
	DASH,
	fractionToPercent,
	money,
	percent,
	quantity,
	signedMoney,
	signedPercent,
	statusTone,
	timeUntil,
	tone,
	when,
	words
} from './format';

describe('trading formats', () => {
	it('writes dollars with cents, and prices with up to four decimals', () => {
		expect(money(1234.5)).toBe('$1,234.50');
		expect(money(0.0594, true)).toBe('$0.0594');
		expect(money(221, true)).toBe('$221.00');
		expect(money(-5)).toBe('-$5.00');
	});

	it('never turns a missing value into a zero', () => {
		for (const format of [money, quantity, percent, signedMoney, signedPercent]) {
			expect([null, undefined, NaN, Infinity].map((v) => format(v as number))).toEqual([
				DASH,
				DASH,
				DASH,
				DASH
			]);
		}
		expect([
			when(null),
			when(''),
			timeUntil(null, 0),
			timeUntil('nonsense', 0),
			words(null),
			words('')
		]).toEqual([DASH, DASH, DASH, DASH, DASH, DASH]);
		expect(fractionToPercent(null)).toBeNull();
	});

	it('keeps quantities exact: up to nine decimals, no trailing zeros', () => {
		expect([10, 0.5, 0.000171, 1234.5678, 0.123456789].map(quantity)).toEqual([
			'10',
			'0.5',
			'0.000171',
			'1,234.5678',
			'0.123456789'
		]);
	});

	it('signs gains and losses in words as well as colour, and zero has neither', () => {
		expect([12.5, -3, 0].map(signedMoney)).toEqual(['+$12.50', '-$3.00', '$0.00']);
		expect([1.25, -0.5, 0].map((v) => signedPercent(v))).toEqual(['+1.25%', '-0.50%', '0.00%']);
		expect([1, -1, 0, null].map(tone)).toEqual(['text-success-ink', 'text-coral-ink', '', '']);
		expect(percent(12.3456, 1)).toBe('12.3%');
		expect(fractionToPercent(0.0124)).toBeCloseTo(1.24, 10);
	});

	it('says when something happened and how long until the next thing', () => {
		expect(when('2026-09-30T14:30:00Z')).toMatch(/Sep 30/);
		expect(when('not a time')).toBe('not a time');
		const now = Date.parse('2026-09-30T14:00:00Z');
		expect([
			timeUntil('2026-09-30T14:00:00Z', now),
			timeUntil('2026-09-30T13:00:00Z', now),
			timeUntil('2026-09-30T16:05:00Z', now),
			timeUntil('2026-09-30T14:09:00Z', now),
			timeUntil('2026-10-03T18:00:00Z', now)
		]).toEqual(['now', 'now', '2h 05m', '0h 09m', '3d 4h']);
	});

	it('reads a state in words and gives each order status its tone', () => {
		expect([words('buy_to_open'), words('partially_filled')]).toEqual([
			'Buy to open',
			'Partially filled'
		]);
		expect(
			['filled', 'canceled', 'rejected', 'expired', 'replaced', 'accepted', null].map(statusTone)
		).toEqual([
			'success',
			'destructive',
			'destructive',
			'destructive',
			'secondary',
			'default',
			'default'
		]);
	});
});
