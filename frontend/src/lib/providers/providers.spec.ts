import { describe, expect, it } from 'vitest';
import {
	accessCounts,
	buildPayload,
	categoryCounts,
	credentialNames,
	filterEndpoints,
	hasPremiumOptions,
	planCounts,
	premiumLabel,
	quotaText,
	seedValues,
	tierLabel,
	validateParams,
	valuesFromExample
} from './form';
import {
	ALPACA_LIKE,
	ALPACA_LIKE_ENDPOINTS,
	CATEGORIES,
	ENDPOINTS,
	TIERED,
	TIERED_ENDPOINTS,
	endpoint,
	param
} from '$lib/testing/provider-fixtures';

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

describe('tiered providers', () => {
	const tiered = (id: string) => TIERED_ENDPOINTS.find((e) => e.id === id)!;

	it('checks whole numbers against the documented bounds, with the same words as the backend', () => {
		const eod = tiered('eod');
		const errors = (limit: string) => validateParams(eod, { symbols: 'AAPL', limit }).limit;
		expect(errors('100')).toBeUndefined();
		expect(errors('1')).toBeUndefined();
		expect(errors('1000')).toBeUndefined();
		expect(errors('0')).toBe('limit must be at least 1');
		expect(errors('1001')).toBe('limit must be at most 1000');
		expect(errors('1.5')).toBe('limit must be a whole number');
		expect(errors('abc')).toBe('limit must be a whole number');
	});

	it('accepts a date or an ISO-8601 timestamp for a datetime and says what is expected otherwise', () => {
		const eod = tiered('eod');
		const problem = (date: string) => validateParams(eod, { symbols: 'AAPL', date }).date;
		for (const ok of [
			'2026-09-29',
			'2020-05-21T00:00:00+0000',
			'2020-05-21T00:00:00+00:00',
			'2020-05-21T09:30:15.123456-04:00',
			'2020-05-21T00:00:00Z',
			'2020-05-21T09:30',
			'2024-02-29'
		])
			expect(problem(ok), ok).toBeUndefined();
		for (const bad of [
			'2020-13-01',
			'2023-02-29',
			'2020-05-21T24:00:00',
			'2020-05-21T10:61',
			'2020-05-21T10:00:60',
			'2020-05-21T10:00:00+2500',
			'2020-05-21 10:00:00',
			'20200521',
			'2020-05-21T',
			'2020-05-21/../x',
			'x'
		])
			expect(problem(bad), bad).toBe(
				'date must be a date (YYYY-MM-DD) or an ISO-8601 timestamp such as 2020-05-21T00:00:00+0000'
			);
		expect(validateParams(eod, { symbols: 'AAPL', date: '' })).toEqual({});
	});

	it('keeps date_from a plain date', () => {
		const errors = validateParams(tiered('eod'), {
			symbols: 'AAPL',
			date_from: '2020-05-21T00:00:00+0000'
		});
		expect(errors.date_from).toBe('date_from must be a date in YYYY-MM-DD format');
	});

	it('leaves a number without bounds unbounded', () => {
		const loose = endpoint('X', {
			params: [param({ name: 'n', type: 'number', minimum: null, maximum: null })]
		});
		expect(validateParams(loose, { n: '-12.5' })).toEqual({});
		expect(validateParams(loose, { n: 'x' })).toEqual({ n: 'n must be a number' });
	});

	it('allows a long list of symbols but not an unbounded one', () => {
		const eod = tiered('eod');
		expect(validateParams(eod, { symbols: Array(300).fill('AAPL').join(',') })).toEqual({});
		expect(validateParams(eod, { symbols: 'A'.repeat(2001) }).symbols).toMatch(/too long/);
	});

	it('words the cost of a request and the premium badge', () => {
		expect(quotaText(1)).toBe('one request');
		expect(quotaText(20)).toBe('20 requests');
		expect(premiumLabel(tiered('intraday'))).toBe('Premium · Basic');
		expect(premiumLabel(endpoint('X'))).toBe('Premium');
	});

	it('counts the endpoints each plan is the first to include and marks the paid plans', () => {
		expect(planCounts(TIERED.plans, TIERED_ENDPOINTS)).toEqual([
			{ name: 'Free', summary: 'End-of-day data.', count: 1, premium: false },
			{ name: 'Basic', summary: 'Adds intraday data and ETF holdings.', count: 2, premium: true },
			{ name: 'Professional', summary: 'Adds commodities.', count: 1, premium: true }
		]);
		expect(planCounts([], TIERED_ENDPOINTS)).toEqual([]);
		const lone = planCounts(
			[
				{ name: 'A', summary: '' },
				{ name: 'B', summary: '' }
			],
			[]
		);
		expect(lone.map((p) => [p.count, p.premium])).toEqual([
			[0, false],
			[0, true]
		]);
	});

	it('filters tiered endpoints by access like any others', () => {
		const all = { search: '', category: 'all', access: 'all' as const };
		expect(accessCounts(TIERED_ENDPOINTS, all)).toEqual({ all: 4, free: 1, premium: 3 });
		expect(
			filterEndpoints(TIERED_ENDPOINTS, { ...all, access: 'premium' }).map((e) => e.id)
		).toEqual(['intraday', 'etfholdings', 'commodities']);
	});
});

describe('tier labels and credentials', () => {
	const [quotes, news] = ALPACA_LIKE_ENDPOINTS;

	it('labels a non-premium endpoint with its plan, or Free when the provider has no tiers', () => {
		expect(tierLabel(quotes)).toBe('Basic');
		expect(tierLabel(endpoint('X'))).toBe('Free');
		expect(tierLabel(by('TIME_SERIES_DAILY'))).toBe('Free');
	});

	it('knows which endpoints have choices or limits that only a higher plan unlocks', () => {
		expect(hasPremiumOptions(quotes)).toBe(true);
		expect(hasPremiumOptions(news)).toBe(false);
		expect(ENDPOINTS.filter(hasPremiumOptions).length).toBeGreaterThan(0);
	});

	it('names one credential variable, or a key and a secret', () => {
		expect(credentialNames(ALPACA_LIKE)).toBe('ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY');
		expect(credentialNames({ key_env: 'ONLY_KEY', secret_env: null })).toBe('ONLY_KEY');
	});

	it('counts a plan that no endpoint needs outright as a paid plan with none starting there', () => {
		expect(
			planCounts(ALPACA_LIKE.plans, ALPACA_LIKE_ENDPOINTS).map((p) => [p.name, p.count, p.premium])
		).toEqual([
			['Basic', 2, false],
			['Algo Trader Plus', 0, true]
		]);
	});
});
