import { describe, expect, it } from 'vitest';
import {
	accessCounts,
	buildPayload,
	categoryCounts,
	filterEndpoints,
	seedValues,
	validateParams,
	valuesFromExample
} from './form';
import { CATEGORIES, ENDPOINTS, endpoint, param } from '$lib/testing/provider-fixtures';

const by = (id: string) => ENDPOINTS.find((e) => e.id === id)!;

describe('validateParams', () => {
	it('requires required parameters and lets optional ones stay empty', () => {
		expect(validateParams(by('TIME_SERIES_DAILY'), {})).toEqual({ symbol: 'symbol is required' });
		expect(validateParams(by('TIME_SERIES_DAILY'), { symbol: 'IBM', outputsize: '' })).toEqual({});
		expect(validateParams(by('TIME_SERIES_DAILY'), { symbol: '   ' })).toEqual({
			symbol: 'symbol is required'
		});
	});

	it('is strict about documented choices, with the choices in the message', () => {
		const errors = validateParams(by('TIME_SERIES_INTRADAY'), { symbol: 'IBM', interval: '2min' });
		expect(errors.interval).toBe('interval must be one of: 1min, 5min, 60min');
		expect(validateParams(by('TIME_SERIES_INTRADAY'), { symbol: 'IBM', interval: '5min' })).toEqual(
			{}
		);
	});

	it('treats suggestions as hints: any text is accepted', () => {
		expect(
			validateParams(by('TIME_SERIES_INTRADAY'), {
				symbol: 'IBM',
				interval: '5min',
				entitlement: 'whatever'
			})
		).toEqual({});
	});

	it.each([
		['adjusted', 'yes', /true or false/],
		['month', '2009-13', /YYYY-MM/],
		['month', '2009-1', /YYYY-MM/]
	])('checks %s = %s', (name, value, message) => {
		expect(
			validateParams(by('TIME_SERIES_INTRADAY'), {
				symbol: 'IBM',
				interval: '5min',
				[name]: value
			})[name]
		).toMatch(message);
	});

	it.each([
		['time_period', 'ten', /must be a number/],
		['time_period', 'NaN', /must be a number/],
		['time_period', 'Infinity', /must be a number/],
		['date', '2017-02-30', /YYYY-MM-DD/],
		['date', '17-02-03', /YYYY-MM-DD/]
	])('checks %s = %s', (name, value, message) => {
		expect(
			validateParams(by('SMA'), { symbol: 'IBM', time_period: '10', [name]: value })[name]
		).toMatch(message);
	});

	it('accepts valid numbers, decimals and dates', () => {
		expect(
			validateParams(by('SMA'), { symbol: 'IBM', time_period: '0.5', date: '2024-02-29' })
		).toEqual({});
	});

	it('does not type-check repeated parameters, which also take relative values', () => {
		const e = by('ANALYTICS_FIXED_WINDOW');
		expect(validateParams(e, { SYMBOLS: 'AAPL', RANGE: ['6month'] })).toEqual({});
		expect(validateParams(e, { SYMBOLS: 'AAPL', RANGE: ['', ''] })).toEqual({
			RANGE: 'RANGE is required'
		});
	});

	it('caps lengths, with a higher cap for symbol lists', () => {
		const e = by('ANALYTICS_FIXED_WINDOW');
		expect(validateParams(e, { SYMBOLS: 'A'.repeat(2000), RANGE: ['full'] })).toEqual({});
		expect(validateParams(e, { SYMBOLS: 'A'.repeat(2001), RANGE: ['full'] }).SYMBOLS).toMatch(
			/too long/
		);
		expect(validateParams(by('TIME_SERIES_DAILY'), { symbol: 'A'.repeat(201) }).symbol).toMatch(
			/too long/
		);
	});

	it('never validates the parameters the server manages', () => {
		expect(
			validateParams(by('TIME_SERIES_DAILY'), { symbol: 'IBM', datatype: 'nonsense' })
		).toEqual({});
	});
});

describe('buildPayload', () => {
	it('trims, drops blanks and managed parameters, and sends repeated parameters as lists', () => {
		expect(
			buildPayload(by('TIME_SERIES_DAILY'), { symbol: ' IBM ', outputsize: '', datatype: 'csv' })
		).toEqual({ symbol: 'IBM' });
		expect(
			buildPayload(by('ANALYTICS_FIXED_WINDOW'), {
				SYMBOLS: 'A,B',
				RANGE: ['2023-07-01', ' ', '2023-08-31']
			})
		).toEqual({ SYMBOLS: 'A,B', RANGE: ['2023-07-01', '2023-08-31'] });
	});
	it('sends a repeated parameter with one value as a one-item list', () => {
		expect(
			buildPayload(by('ANALYTICS_FIXED_WINDOW'), { SYMBOLS: 'A', RANGE: ['full'] }).RANGE
		).toEqual(['full']);
	});
});

describe('seeding', () => {
	it('opens on the first documentation example and gives repeated parameters a slot', () => {
		expect(seedValues(by('TIME_SERIES_INTRADAY'))).toEqual({ symbol: 'IBM', interval: '5min' });
		expect(seedValues(by('ANALYTICS_FIXED_WINDOW'))).toEqual({
			SYMBOLS: 'AAPL,IBM',
			RANGE: ['2023-07-01', '2023-08-31']
		});
		expect(
			seedValues(endpoint('NOEX', { examples: [], params: [param({ name: 'q', multiple: true })] }))
		).toEqual({ q: [''] });
	});
	it('ignores example keys that are not parameters of the endpoint', () => {
		expect(valuesFromExample(by('SMA'), { symbol: 'IBM', function: 'SMA', bogus: 'x' })).toEqual({
			symbol: 'IBM'
		});
	});
});

describe('filters', () => {
	const none = { search: '', category: 'all', access: 'all' as const };
	it('filters by access, category and text together', () => {
		expect(filterEndpoints(ENDPOINTS, { ...none, access: 'premium' }).map((e) => e.id)).toEqual([
			'TIME_SERIES_INTRADAY',
			'REALTIME_OPTIONS'
		]);
		expect(filterEndpoints(ENDPOINTS, { ...none, access: 'free' }).map((e) => e.id)).toEqual([
			'TIME_SERIES_DAILY',
			'SMA',
			'ANALYTICS_FIXED_WINDOW'
		]);
		expect(
			filterEndpoints(ENDPOINTS, { ...none, category: 'indicators' }).map((e) => e.id)
		).toEqual(['SMA', 'ANALYTICS_FIXED_WINDOW']);
		expect(
			filterEndpoints(ENDPOINTS, { search: 'moving', category: 'all', access: 'all' }).map(
				(e) => e.id
			)
		).toEqual(['SMA']);
		expect(
			filterEndpoints(ENDPOINTS, { search: 'sma', category: 'indicators', access: 'free' }).map(
				(e) => e.id
			)
		).toEqual(['SMA']);
		expect(filterEndpoints(ENDPOINTS, { search: 'zzz', category: 'all', access: 'all' })).toEqual(
			[]
		);
	});
	it('counts access under the search and category, so the buttons say what they would show', () => {
		expect(accessCounts(ENDPOINTS, none)).toEqual({ all: 5, free: 3, premium: 2 });
		expect(accessCounts(ENDPOINTS, { ...none, category: 'stocks' })).toEqual({
			all: 2,
			free: 1,
			premium: 1
		});
		expect(accessCounts(ENDPOINTS, { ...none, search: 'options' })).toEqual({
			all: 1,
			free: 0,
			premium: 1
		});
	});
	it('counts categories under the search and access filter', () => {
		const counts = categoryCounts(ENDPOINTS, CATEGORIES, { ...none, access: 'premium' });
		expect(counts.map((c) => [c.id, c.shown, c.shownPremium])).toEqual([
			['stocks', 1, 1],
			['indicators', 0, 0],
			['options', 1, 1]
		]);
	});
});
