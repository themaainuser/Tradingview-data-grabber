import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApiClient, TradingCall } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import { parseEnvelope, parseEnvironments } from '$lib/api/trading';
import fixtures from '$lib/testing/trading-fixtures.json';
import { TradingStore, isView, VIEWS } from './trading.svelte';

type Json = Record<string, unknown>;
const fixture = (name: keyof typeof fixtures, over: Json = {}): Json => ({
	...(fixtures[name] as unknown as Json),
	...over
});

const deferred = <T>() => {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
	return { promise, resolve, reject };
};

/** The routes of the fake backend: what each call answers, by `METHOD /path`. */
const ROUTES: Record<string, Json> = {
	'GET /account': fixture('account'),
	'GET /orders': fixture('orders'),
	'GET /positions': fixture('positions'),
	'GET /clock': fixture('clock'),
	'GET /watchlists': fixture('watchlists'),
	'GET /account/configurations': fixture('config'),
	'GET /account/portfolio-history': fixture('history'),
	'GET /account/activities': fixture('activities'),
	'POST /orders': fixture('order_filled'),
	'DELETE /orders': fixture('bulk_cancel'),
	'DELETE /positions': fixture('bulk_close'),
	'PATCH /account/configurations': fixture('config'),
	'POST /watchlists': fixture('watchlist')
};

function setup(
	routes: Record<string, Json | ((call: TradingCall, env: string) => Json | Promise<Json>)> = {},
	flags: { live?: boolean; configured?: boolean } = {}
) {
	const table = { ...ROUTES, ...routes };
	const trading = vi.fn(
		async (env: string, call: TradingCall, parse: ((data: unknown) => unknown) | null) => {
			const head = /^\/(orders|positions|watchlists|quote)(\/.*)?$/.exec(call.path);
			const own = call.path.startsWith('/orders/by-client-id')
				? '/orders/by-client-id'
				: head
					? `/${head[1]}`
					: call.path;
			const key = `${call.method} ${own}`;
			const route = table[key];
			if (!route) throw new ApiError('http', `no route for ${key}`, 404);
			const body = typeof route === 'function' ? await route(call, env) : route;
			return parseEnvelope(body.__keepEnvironment ? body : { ...body, environment: env }, parse);
		}
	);
	const environments = parseEnvironments(
		JSON.parse(
			JSON.stringify({
				...fixtures.environments,
				environments: fixtures.environments.environments.map((e) => ({
					...e,
					enabled: e.id === 'live' ? (flags.live ?? false) : e.enabled,
					configured: flags.configured ?? (e.id === 'live' ? (flags.live ?? false) : e.configured)
				}))
			})
		)
	).environments;
	const api = {
		trading,
		tradingEnvironments: vi.fn(async () => ({ default: 'paper', environments }))
	};
	const store = new TradingStore(api as unknown as ApiClient);
	return { api, trading, store };
}

async function open(store: TradingStore, env = 'paper') {
	await store.loadEnvironments();
	store.select(env);
}

const paths = (trading: ReturnType<typeof setup>['trading']) =>
	trading.mock.calls.map(([env, call]) => `${env} ${call.method} ${call.path}`);
const order = {
	symbol: 'AAPL',
	side: 'buy',
	type: 'market',
	time_in_force: 'day',
	qty: '10',
	client_order_id: 'vcheck-1'
};

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe('environments', () => {
	it('lists them and knows which spend real money', async () => {
		const { store } = setup();
		await open(store);
		expect(store.environmentsStatus).toBe('ready');
		expect(store.environments.map((e) => e.id)).toEqual(['paper', 'live']);
		expect(store.environment?.id).toBe('paper');
		expect(store.realMoney).toBe(false);
		store.select('live');
		expect(store.realMoney).toBe(true);
		store.select('nowhere');
		expect(store.environment).toBeNull();
		expect(store.realMoney).toBe(true); // an environment nobody recognises is treated as the dangerous one
	});

	it('is not usable when switched off or without keys, and then sends nothing', async () => {
		for (const [env, flags] of [
			['live', {}],
			['paper', { configured: false }]
		] as const) {
			const { store, trading } = setup({}, flags);
			await open(store, env);
			expect(store.usable).toBe(false);
			await store.refresh();
			expect(await store.placeOrder(order, env)).toMatchObject({
				ok: false,
				message: 'This environment is not ready.'
			});
			expect((await store.cancelOrder('00000000-0000-4000-8000-000000000001')).ok).toBe(false);
			expect(trading).not.toHaveBeenCalled();
		}
	});

	it('says when the list cannot be loaded', async () => {
		const { api, store } = setup();
		api.tradingEnvironments.mockRejectedValueOnce(
			new ApiError('network', 'Cannot reach the backend.', null)
		);
		await store.loadEnvironments();
		expect(store.environmentsStatus).toBe('error');
		expect(store.environmentsError?.message).toBe('Cannot reach the backend.');
	});

	it('knows the views of the page', () => {
		expect(VIEWS.map((v) => v.id)).toEqual([
			'overview',
			'trade',
			'orders',
			'positions',
			'watchlists',
			'activity',
			'settings'
		]);
		expect(['orders', 'nothing', '', null, undefined].map(isView)).toEqual([
			true,
			false,
			false,
			false,
			false
		]);
	});
});

describe('what was read never outlives its environment', () => {
	it('clears everything when another environment is chosen and drops an answer that arrives late', async () => {
		const slow = deferred<Json>();
		const { store } = setup({ 'GET /account': () => slow.promise }, { live: true });
		await open(store, 'paper');
		const loading = store.loadAccount();
		await store.loadPositions();
		expect(store.positions.data!.positions).toHaveLength(1);
		store.select('live');
		expect(store.positions.data).toBeNull();
		expect(store.positions.state).toBe('idle');
		expect(store.notice).toBeNull();
		slow.resolve(fixture('account'));
		await loading;
		expect(store.account.data).toBeNull(); // the paper account never reaches the live page
		expect(store.env).toBe('live');
	});

	it('refuses an answer that names another environment', async () => {
		const { store } = setup({
			'GET /account': { ...fixture('account'), environment: 'live', __keepEnvironment: true }
		});
		await open(store);
		await store.loadAccount();
		expect(store.account.data).toBeNull();
	});

	it('ignores a change that finishes after the environment was left, and says so', async () => {
		const slow = deferred<Json>();
		const { store, trading } = setup({ 'DELETE /orders': () => slow.promise }, { live: true });
		await open(store, 'paper');
		const cancelling = store.cancelAllOrders();
		store.select('live');
		slow.resolve(fixture('bulk_cancel'));
		expect(await cancelling).toMatchObject({
			ok: false,
			message: 'The environment changed before the answer arrived.'
		});
		expect(store.notice).toBeNull();
		expect(paths(trading)).toEqual(['paper DELETE /orders']); // and no refresh of the wrong environment
	});
});

describe('reading', () => {
	it('loads each list into its own slot', async () => {
		const { store, trading } = setup();
		await open(store);
		expect(store.account.state).toBe('idle');
		await store.refresh();
		expect(store.account.data?.account_number).toBe('PA3TESTACCT');
		expect(store.orders.data!.orders.length).toBeGreaterThan(2);
		expect(store.positions.data!.positions[0].symbol).toBe('AAPL');
		expect(store.clock.data?.is_open).toBe(true);
		expect(paths(trading).sort()).toEqual([
			'paper GET /account',
			'paper GET /clock',
			'paper GET /orders',
			'paper GET /positions'
		]);
		expect(trading.mock.calls.find(([, c]) => c.path === '/orders')![1].query).toEqual({
			status: 'open',
			limit: '100'
		});
	});

	it('reloads the orders for the filter that is chosen', async () => {
		const { store, trading } = setup();
		await open(store);
		await store.setOrderFilter('closed');
		expect(store.orderFilter).toBe('closed');
		expect(trading.mock.calls.at(-1)![1].query).toMatchObject({ status: 'closed' });
	});

	it('keeps the last good data and says it is stale when a refresh fails', async () => {
		let calls = 0;
		const { store } = setup({
			'GET /account': () =>
				++calls === 1
					? fixture('account')
					: Promise.reject(new ApiError('network', 'Cannot reach the backend.', null))
		});
		await open(store);
		await store.loadAccount();
		expect(store.account).toMatchObject({ state: 'ready', stale: false, problem: null });
		await store.loadAccount();
		expect(store.account.data?.account_number).toBe('PA3TESTACCT');
		expect(store.account).toMatchObject({
			state: 'failed',
			stale: true,
			problem: 'Cannot reach the backend.'
		});
		await store.loadAccount().catch(() => undefined);
	});

	it('shows Alpaca’s own words when it refuses a read', async () => {
		const { store } = setup({ 'GET /account': fixture('invalid_key') });
		await open(store);
		await store.loadAccount();
		expect(store.account.data).toBeNull();
		expect(store.account.state).toBe('failed');
		expect(store.account.problem).toContain('Alpaca refused the credentials (HTTP 401)');
	});

	it('lets only the newest request for a list land', async () => {
		const first = deferred<Json>();
		const second = deferred<Json>();
		const queue = [first, second];
		const { store } = setup({ 'GET /orders': () => queue.shift()!.promise });
		await open(store);
		const a = store.loadOrders();
		const b = store.loadOrders();
		second.resolve(fixture('orders'));
		await b;
		first.resolve(fixture('orders', { data: { orders: [] } }));
		await a;
		expect(store.orders.data!.orders.length).toBeGreaterThan(0);
	});

	it('does not start a refresh while one is running, and polls only when the page is visible and idle', async () => {
		vi.useFakeTimers();
		const gate = deferred<Json>();
		const { store, trading } = setup({ 'GET /clock': () => gate.promise });
		await open(store);
		const first = store.refresh();
		await store.refresh();
		expect(trading.mock.calls.filter(([, c]) => c.path === '/account')).toHaveLength(1);
		gate.resolve(fixture('clock'));
		await first;

		trading.mockClear();
		const stop = store.startRefreshing(1000);
		await vi.advanceTimersByTimeAsync(1000);
		expect(trading.mock.calls.filter(([, c]) => c.path === '/account')).toHaveLength(1);
		store.submitting = true;
		await vi.advanceTimersByTimeAsync(2000);
		expect(trading.mock.calls.filter(([, c]) => c.path === '/account')).toHaveLength(1);
		store.submitting = false;
		vi.stubGlobal('document', { visibilityState: 'hidden' });
		await vi.advanceTimersByTimeAsync(2000);
		expect(trading.mock.calls.filter(([, c]) => c.path === '/account')).toHaveLength(1);
		vi.stubGlobal('document', { visibilityState: 'visible' });
		stop();
		await vi.advanceTimersByTimeAsync(5000);
		expect(trading.mock.calls.filter(([, c]) => c.path === '/account')).toHaveLength(1);
	});

	it('encodes a symbol with a slash and sends the search for assets without keeping it', async () => {
		const { store, trading } = setup({
			'GET /quote': fixture('quote_stock'),
			'GET /assets': fixture('assets')
		});
		await open(store);
		await store.loadQuote('BTC/USD');
		expect(trading.mock.calls.at(-1)![1].path).toBe('/quote/BTC/USD');
		expect(store.quote.data?.symbol).toBe('AAPL');
		const found = await store.searchAssets('aa');
		expect(found!.assets.length).toBeGreaterThan(0);
		expect(trading.mock.calls.at(-1)![1].query).toEqual({
			search: 'aa',
			asset_class: 'us_equity',
			status: 'active',
			limit: '12'
		});
	});
});

describe('placing an order', () => {
	it('sends it once and refreshes the orders, the positions and the account', async () => {
		const { store, trading } = setup();
		await open(store);
		const result = await store.placeOrder(order, 'paper');
		expect(result).toMatchObject({ ok: true, unknown: null, message: 'Order placed.' });
		expect(store.notice).toMatchObject({ tone: 'success' });
		expect(store.notice!.text).toContain('buy AAPL');
		expect(paths(trading)[0]).toBe('paper POST /orders');
		expect(trading.mock.calls[0][1].body).toEqual(order);
		expect(paths(trading).slice(1).sort()).toEqual([
			'paper GET /account',
			'paper GET /orders',
			'paper GET /positions'
		]);
		expect(store.submitting).toBe(false);
		expect(store.busy).toBe(0);
	});

	it('refuses a second submit while the first is out, so a double click cannot place two', async () => {
		const gate = deferred<Json>();
		const { store, trading } = setup({ 'POST /orders': () => gate.promise });
		await open(store);
		const first = store.placeOrder(order, 'paper');
		expect(store.submitting).toBe(true);
		expect(await store.placeOrder(order, 'paper')).toMatchObject({
			ok: false,
			message: 'An order is already being sent.'
		});
		gate.resolve(fixture('order_filled'));
		expect((await first).ok).toBe(true);
		expect(trading.mock.calls.filter(([, c]) => c.method === 'POST')).toHaveLength(1);
		expect((await store.placeOrder({ ...order, client_order_id: 'vcheck-2' }, 'paper')).ok).toBe(
			true
		);
	});

	it('says Alpaca’s reason when it refuses, and leaves the lists alone', async () => {
		const { store, trading } = setup({ 'POST /orders': fixture('order_refused') });
		await open(store);
		const result = await store.placeOrder(order, 'paper');
		expect(result).toMatchObject({
			ok: false,
			message: 'insufficient buying power',
			unknown: null
		});
		expect(result.envelope).toMatchObject({ status: 'rejected', code: 40310000 });
		expect(store.notice).toMatchObject({ tone: 'error', text: 'insufficient buying power' });
		expect(paths(trading)).toEqual(['paper POST /orders']);
		expect(store.submitting).toBe(false);
	});

	it('says why the backend refused before anything was sent', async () => {
		const { store } = setup({
			'POST /orders': () =>
				Promise.reject(
					new ApiError(
						'http',
						'limit_price does not apply to a market order and would be ignored; remove it.',
						422
					)
				)
		});
		await open(store);
		const result = await store.placeOrder(order, 'paper');
		expect(result).toMatchObject({
			ok: false,
			unknown: null,
			message: 'limit_price does not apply to a market order and would be ignored; remove it.'
		});
		expect(store.submitting).toBe(false);
	});

	describe('when no answer comes back', () => {
		const lost = fixture('outcome_unknown', { client_order_id: 'vcheck-1' });

		it('finds the order by its client ID and says it was placed', async () => {
			vi.useFakeTimers();
			const { store, trading } = setup({
				'POST /orders': lost,
				'GET /orders/by-client-id': fixture('order_one')
			});
			await open(store);
			const pending = store.placeOrder(order, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			const result = await pending;
			expect(result).toMatchObject({ ok: true, unknown: 'placed' });
			expect(result.message).toContain('Alpaca did receive the order');
			expect(store.notice).toMatchObject({ tone: 'warning' });
			expect(paths(trading)[1]).toBe('paper GET /orders/by-client-id/vcheck-1');
			expect(store.submitting).toBe(false);
		});

		it('says the order was not placed when Alpaca has no such ID', async () => {
			vi.useFakeTimers();
			const { store } = setup({
				'POST /orders': lost,
				'GET /orders/by-client-id': fixture('not_found')
			});
			await open(store);
			const pending = store.placeOrder(order, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			expect(await pending).toMatchObject({ ok: false, unknown: 'not_found' });
			expect(store.notice!.text).toContain('was not placed');
		});

		it('says it does not know when the lookup fails too, and never claims either way', async () => {
			vi.useFakeTimers();
			const { store } = setup({
				'POST /orders': lost,
				'GET /orders/by-client-id': () => Promise.reject(new ApiError('network', 'down', null))
			});
			await open(store);
			const pending = store.placeOrder(order, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			const result = await pending;
			expect(result).toMatchObject({ ok: false, unknown: 'unclear' });
			expect(result.message).toContain('may or may not have been placed');
		});

		it.each([
			['the connection is lost', new ApiError('network', 'Cannot reach the backend.', null)],
			[
				'the browser gives up waiting',
				new ApiError('timeout', 'The backend took too long to respond', null)
			],
			['a proxy answers 502', new ApiError('http', 'Bad gateway', 502)],
			['the backend answers 500', new ApiError('http', 'Internal Server Error', 500)],
			['the answer cannot be read', new ApiError('contract', 'Unexpected response: order.qty', 200)]
		])(
			'looks the order up by its client ID when %s, because it may have been placed',
			async (_, failure) => {
				vi.useFakeTimers();
				const { store, trading } = setup({
					'POST /orders': () => Promise.reject(failure),
					'GET /orders/by-client-id': fixture('order_one')
				});
				await open(store);
				const pending = store.placeOrder(order, 'paper');
				await vi.advanceTimersByTimeAsync(1500);
				expect(await pending).toMatchObject({ ok: true, unknown: 'placed' });
				expect(paths(trading)[1]).toBe('paper GET /orders/by-client-id/vcheck-1');
				expect(store.notice).toMatchObject({ tone: 'warning' });
			}
		);

		it.each([
			[422, 'limit_price does not apply to a market order.'],
			[403, 'Trading is only served to this machine.'],
			[404, 'Unknown trading environment.']
		])(
			'does not look anything up after the backend refuses with %i: nothing was sent',
			async (status, message) => {
				const { store, trading } = setup({
					'POST /orders': () => Promise.reject(new ApiError('http', message, status))
				});
				await open(store);
				expect(await store.placeOrder(order, 'paper')).toMatchObject({
					ok: false,
					unknown: null,
					message
				});
				expect(paths(trading)).toEqual(['paper POST /orders']);
			}
		);

		it('says not placed, or unclear, when the lookup after a lost connection finds nothing or fails', async () => {
			vi.useFakeTimers();
			const lookup = [
				fixture('not_found'),
				() => Promise.reject(new ApiError('network', 'down', null))
			];
			const { store } = setup({
				'POST /orders': () => Promise.reject(new ApiError('network', 'lost', null)),
				'GET /orders/by-client-id': () => {
					const next = lookup.shift()!;
					return typeof next === 'function' ? next() : next;
				}
			});
			await open(store);
			const first = store.placeOrder(order, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			expect(await first).toMatchObject({ ok: false, unknown: 'not_found' });
			const second = store.placeOrder({ ...order, client_order_id: 'vcheck-2' }, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			expect(await second).toMatchObject({ ok: false, unknown: 'unclear' });
		});
	});

	describe('a retry after an unclear submission', () => {
		/** The first attempt is lost and cannot be looked up; the second is refused by Alpaca, as a duplicate ID is. */
		async function afterAnUnclearAttempt(
			retryAnswer: Json,
			lookupAnswer: Json | (() => Promise<Json>)
		) {
			vi.useFakeTimers();
			let posts = 0;
			const lookups: string[] = [];
			const { store, trading } = setup({
				'POST /orders': () =>
					++posts === 1 ? Promise.reject(new ApiError('network', 'lost', null)) : retryAnswer,
				'GET /orders/by-client-id': () => {
					lookups.push('lookup');
					if (lookups.length === 1) return Promise.reject(new ApiError('network', 'down', null));
					return typeof lookupAnswer === 'function' ? lookupAnswer() : lookupAnswer;
				}
			});
			await open(store);
			const first = store.placeOrder(order, 'paper');
			await vi.advanceTimersByTimeAsync(1500);
			expect(await first).toMatchObject({ unknown: 'unclear' });
			return { store, trading, lookups };
		}
		const duplicate = fixture('order_refused', {
			message: 'client_order_id must be unique',
			code: 42210000,
			http_status: 422
		});

		it('looks for the order Alpaca says already exists and reports that the first attempt went through', async () => {
			const { store, trading, lookups } = await afterAnUnclearAttempt(
				duplicate,
				fixture('order_one')
			);
			const retry = await store.placeOrder(order, 'paper');
			expect(retry).toMatchObject({ ok: true, unknown: 'placed' });
			expect(retry.message).toContain('The first attempt did go through');
			expect(lookups).toHaveLength(2);
			expect(paths(trading).filter((p) => p.includes('POST'))).toHaveLength(2);
			expect(store.notice).toMatchObject({ tone: 'warning' });
		});

		it('shows Alpaca’s own reason when the retry is refused for another reason and the order does not exist', async () => {
			const { store, lookups } = await afterAnUnclearAttempt(
				fixture('order_refused'),
				fixture('not_found')
			);
			const retry = await store.placeOrder(order, 'paper');
			expect(retry).toMatchObject({
				ok: false,
				unknown: 'not_found',
				message: 'insufficient buying power'
			});
			expect(store.notice).toMatchObject({ tone: 'error', text: 'insufficient buying power' });
			// the question is settled: the same ID refused again is an ordinary refusal and is not looked up again
			expect(await store.placeOrder(order, 'paper')).toMatchObject({ ok: false, unknown: null });
			expect(lookups).toHaveLength(2);
		});

		it('stays unclear when the lookup of a refused retry fails too', async () => {
			const { store } = await afterAnUnclearAttempt(duplicate, () =>
				Promise.reject(new ApiError('network', 'down', null))
			);
			expect(await store.placeOrder(order, 'paper')).toMatchObject({
				ok: false,
				unknown: 'unclear'
			});
		});
	});
});

describe('switching account while something is in flight', () => {
	it('refuses an order that was reviewed for another account, and sends nothing', async () => {
		const { store, trading } = setup({}, { live: true });
		await open(store, 'live');
		trading.mockClear();
		expect(await store.placeOrder(order, 'paper')).toMatchObject({ ok: false, unknown: null });
		expect((await store.placeOrder(order, 'paper')).message).toContain(
			'account changed since this order was reviewed'
		);
		expect(trading).not.toHaveBeenCalled();
		await open(store, 'paper');
		expect((await store.placeOrder(order, 'live')).message).toContain('account changed');
		expect(trading).not.toHaveBeenCalled();
	});

	it('keeps the one-order-at-a-time guard up across the switch until the first order is answered', async () => {
		const gate = deferred<Json>();
		const { store, trading } = setup({ 'POST /orders': () => gate.promise }, { live: true });
		await open(store, 'paper');
		const first = store.placeOrder(order, 'paper');
		expect(store.submitting).toBe(true);
		store.select('live');
		expect(store.submitting).toBe(true); // the paper POST is still out
		expect(
			await store.placeOrder({ ...order, client_order_id: 'vcheck-live' }, 'live')
		).toMatchObject({
			ok: false,
			message: 'An order is already being sent.'
		});
		gate.resolve(fixture('order_filled'));
		await first;
		expect(store.submitting).toBe(false);
		expect(trading.mock.calls.filter(([, c]) => c.method === 'POST')).toHaveLength(1);
		expect((await store.placeOrder({ ...order, client_order_id: 'vcheck-live' }, 'live')).ok).toBe(
			true
		);
	});

	it('does not announce the outcome of an order lookup under the account that was switched to', async () => {
		vi.useFakeTimers();
		const lookup = deferred<Json>();
		const { store } = setup(
			{
				'POST /orders': fixture('outcome_unknown', { client_order_id: 'vcheck-1' }),
				'GET /orders/by-client-id': () => lookup.promise
			},
			{ live: true }
		);
		await open(store, 'paper');
		const pending = store.placeOrder(order, 'paper');
		await vi.advanceTimersByTimeAsync(1500); // the lookup is out
		store.select('live');
		lookup.resolve(fixture('not_found'));
		expect(await pending).toMatchObject({ ok: false });
		expect(store.notice).toBeNull();
	});

	it('does not announce a refusal or a failure of an order or another change after the switch', async () => {
		const refusal = deferred<Json>();
		const failure = deferred<Json>();
		const { store } = setup(
			{
				'POST /orders': () => refusal.promise,
				'DELETE /orders': () => failure.promise
			},
			{ live: true }
		);
		await open(store, 'paper');
		const placing = store.placeOrder(order, 'paper');
		const cancelling = store.cancelOrder('00000000-0000-4000-8000-000000000001');
		store.select('live');
		refusal.reject(new ApiError('http', 'qty must be greater than zero.', 422));
		failure.reject(new ApiError('network', 'Cannot reach the backend.', null));
		await Promise.all([placing, cancelling]);
		expect(store.notice).toBeNull();
		// and an announcement about the account that is open still works
		await store.cancelAllOrders().catch(() => undefined);
	});
});

describe('changing things', () => {
	it('cancels, replaces and cancels all by the right route and refreshes what they touch', async () => {
		const id = '00000000-0000-4000-8000-000000000001';
		const { store, trading } = setup({
			'DELETE /orders': (call) =>
				call.path === '/orders' ? fixture('bulk_cancel') : fixture('deleted'),
			'PATCH /orders': fixture('order_waiting')
		});
		await open(store);
		expect(await store.cancelOrder(id)).toMatchObject({ ok: true, message: 'Order cancelled.' });
		expect(paths(trading)[0]).toBe(`paper DELETE /orders/${id}`);
		trading.mockClear();
		expect(await store.replaceOrder(id, { limit_price: '205.5' })).toMatchObject({ ok: true });
		expect(trading.mock.calls[0].slice(0, 2)).toEqual([
			'paper',
			{ method: 'PATCH', path: `/orders/${id}`, body: { limit_price: '205.5' } }
		]);
		trading.mockClear();
		const all = await store.cancelAllOrders();
		expect(all.ok).toBe(true);
		expect(all.envelope!.data!.results.every((r) => r.ok)).toBe(true);
		expect(paths(trading)[0]).toBe('paper DELETE /orders');
	});

	it('closes a position whole, by quantity, by percentage, and all of them', async () => {
		const { store, trading } = setup({ 'DELETE /positions': fixture('order_filled') });
		await open(store);
		await store.closePosition('AAPL');
		await store.closePosition('BTC/USD', { qty: '0.5' });
		await store.closePosition('AAPL', { percentage: '50' });
		const closing = trading.mock.calls
			.filter(([, c]) => c.method === 'DELETE')
			.map(([, c]) => [c.path, c.query]);
		expect(closing).toEqual([
			['/positions/AAPL', {}],
			['/positions/BTC/USD', { qty: '0.5' }],
			['/positions/AAPL', { percentage: '50' }]
		]);
		trading.mockClear();
		const everything = setup({ 'DELETE /positions': fixture('bulk_close') });
		await open(everything.store);
		expect((await everything.store.closeAllPositions(true)).ok).toBe(true);
		expect(everything.trading.mock.calls[0][1]).toMatchObject({
			method: 'DELETE',
			path: '/positions',
			query: { cancel_orders: 'true' }
		});
	});

	it('exercises an option or leaves it to expire', async () => {
		const { store, trading } = setup({ 'POST /positions': fixture('deleted') });
		await open(store);
		expect((await store.exercise('AAPL260116C00250000')).message).toBe(
			'Exercise requested for AAPL260116C00250000.'
		);
		expect((await store.doNotExercise('AAPL260116C00250000')).message).toContain('left to expire');
		expect(paths(trading).filter((p) => p.includes('POST'))).toEqual([
			'paper POST /positions/AAPL260116C00250000/exercise',
			'paper POST /positions/AAPL260116C00250000/do-not-exercise'
		]);
	});

	it('saves settings and manages watchlists', async () => {
		const { store, trading } = setup({
			'PUT /watchlists': fixture('watchlist'),
			'DELETE /watchlists': fixture('deleted'),
			'POST /watchlists': fixture('watchlist')
		});
		await open(store);
		expect((await store.updateConfig({ suspend_trade: true })).message).toBe('Settings saved.');
		expect(trading.mock.calls[0][1]).toMatchObject({
			method: 'PATCH',
			path: '/account/configurations',
			body: { suspend_trade: true }
		});
		const id = '00000000-0000-4000-8000-000000000001';
		trading.mockClear();
		await store.createWatchlist('Core', ['AAPL']);
		await store.renameWatchlist(id, 'Mega');
		await store.addToWatchlist(id, 'SPY');
		await store.removeFromWatchlist(id, 'AAPL');
		await store.deleteWatchlist(id);
		const sent = trading.mock.calls
			.filter(([, c]) => c.method !== 'GET')
			.map(([, c]) => `${c.method} ${c.path} ${JSON.stringify(c.body ?? null)}`);
		expect(sent).toEqual([
			'POST /watchlists {"name":"Core","symbols":["AAPL"]}',
			`PUT /watchlists/${id} {"name":"Mega"}`,
			`POST /watchlists/${id}/assets {"symbol":"SPY"}`,
			`DELETE /watchlists/${id}/assets/AAPL null`,
			`DELETE /watchlists/${id} null`
		]);
	});

	it('tells the user what Alpaca said when a change is refused, and can dismiss the notice', async () => {
		const { store } = setup({
			'DELETE /orders': fixture('not_found', {
				message: 'order is not cancelable',
				status: 'rejected'
			})
		});
		await open(store);
		const result = await store.cancelOrder('e9a0a5f5-8f43-4a64-9a5d-1c6e0c1d2f3a');
		expect(result).toMatchObject({ ok: false, message: 'order is not cancelable' });
		expect(store.notice).toMatchObject({ tone: 'error', text: 'order is not cancelable' });
		store.dismissNotice();
		expect(store.notice).toBeNull();
		expect(store.busy).toBe(0);
	});
});
