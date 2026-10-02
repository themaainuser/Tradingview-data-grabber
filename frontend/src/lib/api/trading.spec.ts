import { describe, expect, it, vi } from 'vitest';
import { createApiClient, TRADING_HEADER } from './client';
import {
	parseAccount,
	parseActivities,
	parseAsset,
	parseAssets,
	parseBulk,
	parseCalendar,
	parseClock,
	parseConfig,
	parseContracts,
	parseEnvelope,
	parseEnvironments,
	parseHistory,
	parseOrder,
	parseOrders,
	parsePosition,
	parsePositions,
	parseQuote,
	parseWatchlist,
	parseWatchlists
} from './trading';
import fixtures from '$lib/testing/trading-fixtures.json';

// Every answer below is what the real backend produced (tests/trading_fixtures.py), so a field the backend
// renames or retypes fails here instead of in front of an order button.
const answer = (name: keyof typeof fixtures) =>
	fixtures[name] as unknown as Record<string, unknown>;
const parse = <T>(name: keyof typeof fixtures, parser: (data: unknown) => T) =>
	parseEnvelope(answer(name), parser);

describe('the real answers of the backend', () => {
	it('reads the environments', () => {
		const { default: first, environments } = parseEnvironments(fixtures.environments);
		expect(first).toBe('paper');
		expect(environments.map((e) => [e.id, e.real_money, e.enabled, e.configured])).toEqual([
			['paper', false, true, true],
			['live', true, false, false]
		]);
		expect(environments[1].note).toContain('ALPACA_ENABLE_LIVE_TRADING=true');
		expect(environments[0].fallback_key_env).toBe('ALPACA_API_KEY_ID');
	});

	it('reads the account as numbers', () => {
		const envelope = parse('account', parseAccount);
		expect(envelope).toMatchObject({
			environment: 'paper',
			status: 'ok',
			http_status: 200,
			outcome_unknown: false
		});
		expect(envelope.data).toMatchObject({
			account_number: 'PA3TESTACCT',
			status: 'ACTIVE',
			multiplier: 2,
			trading_blocked: false,
			shorting_enabled: true
		});
		expect(typeof envelope.data?.equity).toBe('number');
		expect(envelope.data?.day_change).not.toBeNull();
	});

	it('reads the settings, the equity curve, the market and the activity', () => {
		expect(parse('config', parseConfig).data).toMatchObject({
			suspend_trade: false,
			max_margin_multiplier: '2',
			max_options_trading_level: 2
		});
		const history = parse('history', parseHistory).data!;
		expect(history.timestamp).toHaveLength(3);
		expect(history.equity).toEqual([100000, 100250.5, null]);
		expect(parse('clock', parseClock).data).toMatchObject({ is_open: true });
		expect(parse('calendar', parseCalendar).data!.days[1]).toMatchObject({
			date: '2026-10-02',
			close: '13:00'
		});
		const fill = parse('activities', parseActivities).data!.activities[0];
		expect(fill).toMatchObject({ activity_type: 'FILL', symbol: 'AAPL', side: 'buy' });
		expect(typeof fill.qty).toBe('number');
	});

	it('reads orders of every shape, with their exit and option legs', () => {
		expect(parse('order_filled', parseOrder).data).toMatchObject({
			status: 'filled',
			filled_qty: 10,
			cancelable: false,
			open: false,
			client_order_id: 'fixture-1'
		});
		expect(parse('order_waiting', parseOrder).data).toMatchObject({
			status: 'accepted',
			cancelable: true,
			limit_price: 300,
			time_in_force: 'gtc'
		});
		const bracket = parse('order_bracket', parseOrder).data!;
		expect(bracket.order_class).toBe('bracket');
		expect(bracket.legs.map((leg) => [leg.type, leg.status])).toEqual([
			['limit', 'held'],
			['stop', 'held']
		]);
		const multi = parse('order_multileg', parseOrder).data!;
		expect(multi.legs.map((leg) => leg.symbol)).toEqual([
			'AAPL260116C00250000',
			'AAPL260116P00240000'
		]);
		const all = parse('orders', parseOrders).data!.orders;
		expect(all.length).toBeGreaterThan(3);
		expect(parse('order_one', parseOrder).data!.id).toBe(
			all.find((o) => o.client_order_id === 'fixture-1')!.id
		);
	});

	it('reads positions, assets, contracts and quotes', () => {
		expect(parse('positions', parsePositions).data!.positions[0]).toMatchObject({
			symbol: 'AAPL',
			qty: 10,
			side: 'long',
			asset_class: 'us_equity'
		});
		expect(parse('position', parsePosition).data!.market_value).toBe(2210);
		const assets = parse('assets', parseAssets).data!;
		expect(assets.total).toBe(assets.assets.length);
		expect(parse('asset', parseAsset).data).toMatchObject({
			symbol: 'AAPL',
			tradable: true,
			fractionable: true,
			attributes: ['has_options']
		});
		expect(parse('contracts', parseContracts).data!.contracts[0]).toMatchObject({
			symbol: 'AAPL260116C00250000',
			strike_price: 250,
			multiplier: 100,
			type: 'call'
		});
		expect(parse('quote_stock', parseQuote).data).toMatchObject({
			kind: 'us_equity',
			bid: 220.95,
			ask: 221.05,
			greeks: null
		});
		expect(parse('quote_option', parseQuote).data!.greeks).toMatchObject({ delta: 0.5 });
	});

	it('reads watchlists and the answers to cancel-all and close-all', () => {
		expect(parse('watchlist', parseWatchlist).data!.assets.map((a) => a.symbol)).toEqual([
			'AAPL',
			'TSLA'
		]);
		expect(parse('watchlists', parseWatchlists).data!.watchlists[0]).toMatchObject({
			name: 'Core',
			assets: []
		});
		expect(parse('bulk_cancel', parseBulk).data!.results.every((r) => r.ok && r.id)).toBe(true);
		const closed = parse('bulk_close', parseBulk).data!.results[0];
		expect(closed).toMatchObject({ symbol: 'AAPL', ok: true });
		expect(closed.order).toMatchObject({ side: 'sell' });
	});

	it('keeps a refusal, a missing key and an unknown outcome as what they are, with no data', () => {
		expect(parse('order_refused', parseOrder)).toMatchObject({
			status: 'rejected',
			code: 40310000,
			message: 'insufficient buying power',
			http_status: 403,
			data: null
		});
		expect(parse('invalid_key', parseAccount)).toMatchObject({ status: 'invalid_key', data: null });
		expect(parse('not_configured', parseAccount)).toMatchObject({
			status: 'not_configured',
			fetched_at: null,
			data: null
		});
		expect(parse('not_found', parseOrder)).toMatchObject({ status: 'not_found', data: null });
		const unknown = parse('outcome_unknown', parseOrder);
		expect(unknown).toMatchObject({
			status: 'upstream_error',
			outcome_unknown: true,
			client_order_id: 'fixture-6',
			data: null
		});
		expect(unknown.message).toContain('may still have been processed');
		expect(parseEnvelope(answer('deleted'), null)).toMatchObject({ status: 'ok', data: null });
	});
});

describe('a payload that breaks the contract is refused', () => {
	const clone = () => JSON.parse(JSON.stringify(fixtures));

	it('refuses a field of the wrong kind instead of drawing it', () => {
		const bad = clone();
		bad.account.data.equity = '100000.00';
		expect(() => parseEnvelope(bad.account, parseAccount)).toThrow(
			/account\.equity should be a finite number/
		);
		const flag = clone();
		flag.orders.data.orders[0].cancelable = 'yes';
		expect(() => parseEnvelope(flag.orders, parseOrders)).toThrow(/orders\[0\]\.cancelable/);
		const nested = clone();
		nested.order_bracket.data.legs[1].filled_qty = 'lots';
		expect(() => parseEnvelope(nested.order_bracket, parseOrder)).toThrow(
			/order\.legs\[1\]\.filled_qty/
		);
	});

	it('refuses an unknown status, a missing envelope field and duplicate environments', () => {
		expect(() => parseEnvelope({ ...answer('account'), status: 'maybe' }, parseAccount)).toThrow(
			/status/
		);
		expect(() =>
			parseEnvelope({ ...answer('account'), elapsed_ms: undefined }, parseAccount)
		).toThrow(/elapsed_ms/);
		expect(() => parseEnvelope('ok', parseAccount)).toThrow(/response/);
		const twice = clone();
		twice.environments.environments.push(twice.environments.environments[0]);
		expect(() => parseEnvironments(twice.environments)).toThrow(/unique ids/);
	});

	it('refuses an equity curve whose columns do not line up with its times', () => {
		const bad = clone();
		bad.history.data.equity.pop();
		expect(() => parseEnvelope(bad.history, parseHistory)).toThrow(
			/history\.equity should be an array of 3 values/
		);
	});

	it('treats a field Alpaca did not send as missing, not as an error', () => {
		const sparse = clone();
		delete sparse.account.data.sma;
		delete sparse.positions.data.positions[0].unrealized_pl;
		expect(parseEnvelope(sparse.account, parseAccount).data!.sma).toBeNull();
		expect(
			parseEnvelope(sparse.positions, parsePositions).data!.positions[0].unrealized_pl
		).toBeNull();
	});
});

describe('the client', () => {
	function client(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
		const fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) =>
			respond(String(url), init ?? {})
		);
		return {
			fetch,
			api: createApiClient({ fetch: fetch as unknown as typeof globalThis.fetch, retryDelayMs: 1 })
		};
	}
	const json = (body: unknown, status = 200) =>
		new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

	it('reads with GET, builds the query and leaves empty values out', async () => {
		const { api, fetch } = client(() => json(fixtures.orders));
		const envelope = await api.trading(
			'paper',
			{
				method: 'GET',
				path: '/orders',
				query: { status: 'all', limit: '50', symbols: '', after: undefined }
			},
			parseOrders
		);
		expect(envelope.data!.orders.length).toBeGreaterThan(0);
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe('/api/trading/paper/orders?status=all&limit=50');
		expect(init?.method ?? 'GET').toBe('GET');
		expect(new Headers(init?.headers).has(TRADING_HEADER)).toBe(false);
	});

	it('marks every change as the dashboard’s own and sends the body as JSON', async () => {
		const { api, fetch } = client(() => json(fixtures.order_filled));
		await api.trading(
			'paper',
			{ method: 'POST', path: '/orders', body: { symbol: 'AAPL', qty: '1' } },
			parseOrder
		);
		for (const method of ['PATCH', 'PUT', 'DELETE'] as const)
			await api.trading('paper', { method, path: '/orders/x' }, null);
		const calls = fetch.mock.calls.map(([url, init]) => ({
			url: String(url),
			method: init?.method,
			headers: new Headers(init?.headers),
			body: init?.body
		}));
		expect(calls.map((c) => c.method)).toEqual(['POST', 'PATCH', 'PUT', 'DELETE']);
		expect(calls.every((c) => c.headers.get(TRADING_HEADER) === '1')).toBe(true);
		expect(calls[0].headers.get('Content-Type')).toBe('application/json');
		expect(calls[0].body).toBe('{"symbol":"AAPL","qty":"1"}');
		expect(calls[1].headers.has('Content-Type')).toBe(false);
		expect(calls[1].body).toBeUndefined();
	});

	it('retries a read after a server fault but never a change', async () => {
		let reads = 0;
		const flaky = client(() =>
			++reads < 3 ? json({ detail: 'down' }, 503) : json(fixtures.account)
		);
		expect(
			(await flaky.api.trading('paper', { method: 'GET', path: '/account' }, parseAccount)).status
		).toBe('ok');
		expect(flaky.fetch).toHaveBeenCalledTimes(3);
		const failing = client(() => json({ detail: 'down' }, 503));
		await expect(
			failing.api.trading('paper', { method: 'POST', path: '/orders', body: {} }, parseOrder)
		).rejects.toMatchObject({ kind: 'http', status: 503 });
		expect(failing.fetch).toHaveBeenCalledTimes(1);
	});

	it('says why the backend refused: a 403 guard, a 422 sentence, an unreachable server', async () => {
		await expect(
			client(() => json({ detail: 'Live trading is switched off.' }, 403)).api.trading(
				'live',
				{ method: 'GET', path: '/account' },
				parseAccount
			)
		).rejects.toMatchObject({ message: 'Live trading is switched off.', status: 403 });
		await expect(
			client(() => json({ detail: 'qty must be greater than zero.' }, 422)).api.trading(
				'paper',
				{ method: 'POST', path: '/orders', body: {} },
				parseOrder
			)
		).rejects.toMatchObject({ message: 'qty must be greater than zero.' });
		const down = createApiClient({
			fetch: (async () => Promise.reject(new TypeError('failed'))) as unknown as typeof fetch,
			retries: 0
		});
		await expect(
			down.trading('paper', { method: 'POST', path: '/orders', body: {} }, parseOrder)
		).rejects.toMatchObject({ kind: 'network' });
	});

	it('puts the environment in the path, encoded, and lists the environments', async () => {
		const { api, fetch } = client((url) =>
			json(url.endsWith('/environments') ? fixtures.environments : fixtures.account)
		);
		await api.trading('pa per', { method: 'GET', path: '/account' }, parseAccount);
		expect(fetch.mock.calls[0][0]).toBe('/api/trading/pa%20per/account');
		expect((await api.tradingEnvironments()).environments).toHaveLength(2);
		expect(fetch.mock.calls[1][0]).toBe('/api/trading/environments');
	});
});
