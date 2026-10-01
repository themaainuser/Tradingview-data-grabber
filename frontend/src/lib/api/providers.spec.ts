import { describe, expect, it } from 'vitest';
import { parseCatalog, parseProviders, parseQueryResponse } from './providers';
import {
	ALL_VIEWS,
	CATEGORIES,
	ENDPOINTS,
	TIERED,
	TIERED_CATEGORIES,
	TIERED_ENDPOINTS,
	catalog,
	endpoint,
	failure,
	provider,
	response,
	seriesView
} from '$lib/testing/provider-fixtures';

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

/** The failure the validators raise: an ApiError of kind 'contract' (never just any error). */
const contractError = (match?: RegExp) =>
	expect.objectContaining({
		name: 'ApiError',
		kind: 'contract',
		message: match ? expect.stringMatching(match) : expect.any(String)
	});

describe('parseQueryResponse', () => {
	it('accepts a response that carries every kind of view', () => {
		const parsed = parseQueryResponse(response({ views: ALL_VIEWS() }));
		expect(parsed.views.map((v) => v.kind)).toEqual([
			'facts',
			'series',
			'series',
			'bars',
			'feed',
			'heatmap',
			'table',
			'text'
		]);
	});

	it('accepts every failure status with its message and no views', () => {
		for (const status of [
			'empty',
			'not_configured',
			'rate_limited',
			'premium_required',
			'invalid_key',
			'invalid_request',
			'upstream_error'
		] as const) {
			expect(parseQueryResponse(failure(status, 'why')).status).toBe(status);
		}
	});

	it('rejects a failed query that still carries views: no data is drawn when the provider refused', () => {
		const bad = { ...failure('premium_required', 'premium'), views: [seriesView()] };
		expect(() => parseQueryResponse(clone(bad))).toThrow(contractError());
	});

	it('rejects a failed query without a message', () => {
		expect(() =>
			parseQueryResponse(clone({ ...failure('rate_limited', 'x'), message: null }))
		).toThrow(contractError());
	});

	it('rejects an unknown status and an unknown view kind', () => {
		expect(() => parseQueryResponse(clone({ ...response(), status: 'maybe' }))).toThrow(/status/);
		expect(() =>
			parseQueryResponse(
				clone({ ...response(), views: [{ kind: 'pie', id: 'x', title: 'x', subtitle: null }] })
			)
		).toThrow(/view kind/);
	});

	it('rejects a series whose values do not line up with its time axis', () => {
		const view = clone(seriesView(5));
		view.series[0].values.pop();
		expect(() => parseQueryResponse(clone(response({ views: [view] })))).toThrow(contractError());
	});

	it('rejects a series that is not strictly increasing in time', () => {
		const view = clone(seriesView(5));
		view.time[3] = view.time[2];
		expect(() => parseQueryResponse(clone(response({ views: [view] })))).toThrow(
			/strictly increasing/
		);
	});

	it('rejects a truncated flag that disagrees with the counts', () => {
		expect(() =>
			parseQueryResponse(
				clone(response({ views: [seriesView(5, { truncated: true, total_points: 5 })] }))
			)
		).toThrow(/truncated/);
		expect(() =>
			parseQueryResponse(
				clone(response({ views: [seriesView(5, { truncated: false, total_points: 9 })] }))
			)
		).toThrow(/truncated/);
	});

	it('rejects a table row with the wrong number of cells', () => {
		const table = clone(ALL_VIEWS().find((v) => v.kind === 'table')!) as { rows: unknown[][] };
		table.rows[1].pop();
		expect(() => parseQueryResponse(clone(response({ views: [table as never] })))).toThrow(
			contractError()
		);
	});

	it('rejects a non-numeric number and a heatmap of the wrong shape', () => {
		const view = clone(seriesView(3)) as unknown as { series: { values: unknown[] }[] };
		view.series[0].values[0] = 'oops';
		expect(() => parseQueryResponse(clone(response({ views: [view as never] })))).toThrow(
			contractError()
		);
		const heat = clone(ALL_VIEWS().find((v) => v.kind === 'heatmap')!) as { values: unknown[][] };
		heat.values.pop();
		expect(() => parseQueryResponse(clone(response({ views: [heat as never] })))).toThrow(
			contractError()
		);
	});

	it('keeps nulls as nulls rather than turning them into zero', () => {
		const view = clone(seriesView(4));
		view.series[3].values[1] = null;
		const parsed = parseQueryResponse(clone(response({ views: [view] })));
		expect(parsed.views[0].kind === 'series' && parsed.views[0].series[3].values[1]).toBeNull();
	});

	it('rejects something that is not an object', () => {
		expect(() => parseQueryResponse(null)).toThrow(contractError());
		expect(() => parseQueryResponse([])).toThrow(contractError());
	});
});

describe('parseCatalog / parseProviders', () => {
	it('accepts a catalog and keeps premium flags and parameter notes', () => {
		const parsed = parseCatalog(clone(catalog()));
		expect(parsed.endpoints.filter((e) => e.premium).map((e) => e.id)).toEqual([
			'TIME_SERIES_INTRADAY',
			'REALTIME_OPTIONS'
		]);
		expect(parsed.endpoints[0].params.find((p) => p.name === 'outputsize')?.premium_note).toContain(
			'premium'
		);
		expect(parsed.endpoints[0].params.find((p) => p.name === 'datatype')?.managed).toBe(true);
	});

	it('rejects duplicate endpoint ids and endpoints in an unknown category', () => {
		const dup = { ...catalog(), endpoints: [ENDPOINTS[0], ENDPOINTS[0]] };
		expect(() => parseCatalog(clone(dup))).toThrow(/unique/);
		const stray = { ...catalog(), endpoints: [endpoint('X', { category: 'nowhere' })] };
		expect(() => parseCatalog(clone(stray))).toThrow(/category/);
		expect(CATEGORIES.length).toBe(3);
	});

	it('rejects an unknown parameter type', () => {
		const bad = clone(catalog());
		(bad.endpoints[0].params[0] as { type: string }).type = 'colour';
		expect(() => parseCatalog(bad)).toThrow(/type/);
	});

	it('accepts a provider list and rejects duplicate provider ids', () => {
		expect(
			parseProviders({ providers: [provider(), provider({ id: 'other', name: 'Other' })] })
		).toHaveLength(2);
		expect(() => parseProviders({ providers: [provider(), provider()] })).toThrow(/unique/);
	});

	it('keeps plans, the plan of each endpoint, quota costs, bounds and premium choices', () => {
		const tiered = clone({ ...catalog(TIERED, TIERED_ENDPOINTS), categories: TIERED_CATEGORIES });
		const parsed = parseCatalog(tiered);
		const find = (id: string) => parsed.endpoints.find((e) => e.id === id)!;
		expect(parsed.provider.plans.map((p) => p.name)).toEqual(['Free', 'Basic', 'Professional']);
		expect(parsed.endpoints.map((e) => [e.id, e.plan, e.request_cost])).toEqual([
			['eod', 'Free', 1],
			['intraday', 'Basic', 1],
			['etfholdings', 'Basic', 20],
			['commodities', 'Professional', 1]
		]);
		const limit = find('eod').params.find((p) => p.name === 'limit')!;
		expect([limit.type, limit.minimum, limit.maximum]).toEqual(['integer', 1, 1000]);
		expect(find('intraday').params.find((p) => p.name === 'interval')?.premium_values).toEqual([
			'1min'
		]);
		expect(parseCatalog(clone(catalog())).endpoints[0].plan).toBeNull();
	});

	it('rejects a premium choice that is not one of the choices', () => {
		const bad = clone({ ...catalog(TIERED, TIERED_ENDPOINTS), categories: TIERED_CATEGORIES });
		bad.endpoints[1].params[1].premium_values = ['2min'];
		expect(() => parseCatalog(bad)).toThrow(/premium_values/);
	});

	it('rejects a quota cost that is not a whole number of at least 1', () => {
		for (const cost of [0, 1.5, -2]) {
			const bad = clone({ ...catalog(TIERED, TIERED_ENDPOINTS), categories: TIERED_CATEGORIES });
			bad.endpoints[0].request_cost = cost;
			expect(() => parseCatalog(bad)).toThrow(/request_cost/);
		}
	});

	it('rejects a provider whose plans are not a list of named plans', () => {
		const bad = clone(provider()) as unknown as Record<string, unknown>;
		bad.plans = [{ name: 'Free' }];
		expect(() => parseProviders({ providers: [bad] })).toThrow(/plans/);
		delete bad.plans;
		expect(() => parseProviders({ providers: [bad] })).toThrow(/plans/);
	});
});
