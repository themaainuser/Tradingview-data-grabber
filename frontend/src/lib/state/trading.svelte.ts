import type { ApiClient, TradingCall } from '$lib/api/client';
import { isAbort, toApiError, type ApiError } from '$lib/api/errors';
import {
	parseAccount,
	parseActivities,
	parseAssets,
	parseBulk,
	parseCalendar,
	parseClock,
	parseConfig,
	parseContracts,
	parseHistory,
	parseOrder,
	parseOrders,
	parsePositions,
	parseQuote,
	parseWatchlist,
	parseWatchlists,
	type Account,
	type AccountConfig,
	type Activity,
	type Asset,
	type Clock,
	type Contract,
	type Envelope,
	type MarketDay,
	type Order,
	type PortfolioHistory,
	type Position,
	type Quote,
	type TradingEnvironment,
	type Watchlist
} from '$lib/api/trading';

/**
 * The trading page's state: the environment, the account and everything read from it, and the actions
 * that change it.
 *
 * Two rules matter more than the rest. What was read from one environment never outlives it: choosing
 * another clears everything, and an answer that arrives for the environment you left is dropped, so
 * paper numbers can never sit under a live label. And nothing that changes something is sent twice:
 * one submit at a time, no retries, and an order whose outcome is unknown is looked up by its client ID
 * before anyone is told anything.
 */

export type ViewName =
	'overview' | 'trade' | 'orders' | 'positions' | 'watchlists' | 'activity' | 'settings';
export const VIEWS: readonly { id: ViewName; label: string }[] = [
	{ id: 'overview', label: 'Overview' },
	{ id: 'trade', label: 'Trade' },
	{ id: 'orders', label: 'Orders' },
	{ id: 'positions', label: 'Positions' },
	{ id: 'watchlists', label: 'Watchlists' },
	{ id: 'activity', label: 'Activity' },
	{ id: 'settings', label: 'Settings' }
];
export const isView = (value: string | null | undefined): value is ViewName =>
	VIEWS.some((v) => v.id === value);

/** One thing read from Alpaca. Failing to refresh keeps the last good data and says it is stale. */
export class Resource<T> {
	state = $state<'idle' | 'loading' | 'ready' | 'failed'>('idle');
	envelope = $state.raw<Envelope<T> | null>(null);
	/** The last answer that was not `ok`, or `null` after one that was. */
	refusal = $state.raw<Envelope<T> | null>(null);
	error = $state.raw<ApiError | null>(null);

	data = $derived(this.envelope?.status === 'ok' ? this.envelope.data : null);
	problem = $derived(
		this.error?.message ??
			this.refusal?.message ??
			(this.refusal ? `Alpaca answered ${this.refusal.status}.` : null)
	);
	stale = $derived(this.data !== null && this.problem !== null);

	reset(): void {
		this.state = 'idle';
		this.envelope = null;
		this.refusal = null;
		this.error = null;
	}
}

export interface Notice {
	tone: 'success' | 'warning' | 'error';
	text: string;
	at: number;
}

export interface ActionResult<T> {
	ok: boolean;
	envelope: Envelope<T> | null;
	/** Set when the request never produced an answer (backend down, a guard said no, a 422). */
	error: ApiError | null;
	message: string;
}

/** What became of an order whose submission got no answer. */
export type UnknownOutcome = 'placed' | 'not_found' | 'unclear';

export interface PlaceResult extends ActionResult<Order> {
	unknown: UnknownOutcome | null;
}

const REFRESH_MS = 5000;
const LOOKUP_DELAY_MS = 1500;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const encodeSymbol = (symbol: string) => symbol.split('/').map(encodeURIComponent).join('/');

export class TradingStore {
	readonly #api: ApiClient;
	readonly #controllers = new Map<object, AbortController>();

	environments = $state.raw<TradingEnvironment[]>([]);
	environmentsStatus = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	environmentsError = $state.raw<ApiError | null>(null);
	env = $state<string | null>(null);

	readonly account = new Resource<Account>();
	readonly config = new Resource<AccountConfig>();
	readonly history = new Resource<PortfolioHistory>();
	readonly clock = new Resource<Clock>();
	readonly orders = new Resource<{ orders: Order[] }>();
	readonly positions = new Resource<{ positions: Position[] }>();
	readonly watchlists = new Resource<{ watchlists: Watchlist[] }>();
	readonly activities = new Resource<{ activities: Activity[]; next_page_token: string | null }>();
	readonly calendar = new Resource<{ days: MarketDay[] }>();
	readonly quote = new Resource<Quote>();
	readonly contracts = new Resource<{ contracts: Contract[]; next_page_token: string | null }>();

	/** The order list's filter: which orders are shown. */
	orderFilter = $state<'open' | 'closed' | 'all'>('open');
	notice = $state.raw<Notice | null>(null);
	submitting = $state(false);
	busy = $state(0);
	refreshing = $state(false);

	environment = $derived(this.environments.find((e) => e.id === this.env) ?? null);
	/** True when this environment spends real money. Unknown environments count as real. */
	realMoney = $derived(this.environment?.real_money ?? true);
	/** Whether requests can be made: the environment is switched on and has keys. */
	usable = $derived(!!this.environment && this.environment.enabled && this.environment.configured);

	constructor(api: ApiClient) {
		this.#api = api;
	}

	// --- environments -------------------------------------------------------------------------------

	async loadEnvironments(): Promise<void> {
		this.environmentsStatus = 'loading';
		this.environmentsError = null;
		try {
			this.environments = (await this.#api.tradingEnvironments()).environments;
			this.environmentsStatus = 'ready';
		} catch (error) {
			if (isAbort(error)) return;
			this.environmentsError = toApiError(error);
			this.environmentsStatus = 'error';
		}
	}

	/** Applies the address: which environment is open. Clears everything read from the one before. */
	select(env: string | null): void {
		if (env === this.env) return;
		for (const controller of this.#controllers.values()) controller.abort();
		this.#controllers.clear();
		this.env = env;
		for (const resource of [
			this.account,
			this.config,
			this.history,
			this.clock,
			this.orders,
			this.positions,
			this.watchlists,
			this.activities,
			this.calendar,
			this.quote,
			this.contracts
		])
			resource.reset();
		this.notice = null;
		this.submitting = false;
		this.refreshing = false;
	}

	// --- reading ----------------------------------------------------------------------------------------

	async #read<T>(
		resource: Resource<T>,
		call: TradingCall,
		parse: (data: unknown) => T
	): Promise<void> {
		const env = this.env;
		if (!env || !this.usable) return;
		this.#controllers.get(resource)?.abort();
		const controller = new AbortController();
		this.#controllers.set(resource, controller);
		if (resource.envelope === null) resource.state = 'loading';
		try {
			const envelope = await this.#api.trading(env, call, parse, { signal: controller.signal });
			if (
				this.env !== env ||
				envelope.environment !== env ||
				this.#controllers.get(resource) !== controller
			)
				return;
			resource.error = null;
			if (envelope.status === 'ok') {
				resource.envelope = envelope;
				resource.refusal = null;
				resource.state = 'ready';
			} else {
				resource.refusal = envelope;
				resource.state = 'failed';
			}
		} catch (error) {
			if (isAbort(error) || this.env !== env || this.#controllers.get(resource) !== controller)
				return;
			resource.error = toApiError(error);
			resource.state = 'failed';
		}
	}

	loadAccount = () => this.#read(this.account, { method: 'GET', path: '/account' }, parseAccount);
	loadConfig = () =>
		this.#read(this.config, { method: 'GET', path: '/account/configurations' }, parseConfig);
	loadClock = () => this.#read(this.clock, { method: 'GET', path: '/clock' }, parseClock);
	loadPositions = () =>
		this.#read(this.positions, { method: 'GET', path: '/positions' }, parsePositions);
	loadWatchlists = () =>
		this.#read(this.watchlists, { method: 'GET', path: '/watchlists' }, parseWatchlists);
	loadOrders = () =>
		this.#read(
			this.orders,
			{ method: 'GET', path: '/orders', query: { status: this.orderFilter, limit: '100' } },
			parseOrders
		);
	loadHistory = (period = '1M', timeframe = '1D') =>
		this.#read(
			this.history,
			{ method: 'GET', path: '/account/portfolio-history', query: { period, timeframe } },
			parseHistory
		);
	loadActivities = (query: Record<string, string> = {}) =>
		this.#read(
			this.activities,
			{ method: 'GET', path: '/account/activities', query: { page_size: '50', ...query } },
			parseActivities
		);
	loadCalendar = (start: string, end: string) =>
		this.#read(
			this.calendar,
			{ method: 'GET', path: '/calendar', query: { start, end } },
			parseCalendar
		);
	loadQuote = (symbol: string) =>
		this.#read(this.quote, { method: 'GET', path: `/quote/${encodeSymbol(symbol)}` }, parseQuote);
	loadContracts = (query: Record<string, string>) =>
		this.#read(
			this.contracts,
			{ method: 'GET', path: '/options/contracts', query: { limit: '100', ...query } },
			parseContracts
		);

	setOrderFilter(filter: 'open' | 'closed' | 'all'): Promise<void> {
		this.orderFilter = filter;
		return this.loadOrders();
	}

	/** The lists that change as the market moves: the account, orders, positions and the market clock. */
	async refresh(): Promise<void> {
		if (this.refreshing || !this.usable) return;
		this.refreshing = true;
		try {
			await Promise.all([
				this.loadAccount(),
				this.loadOrders(),
				this.loadPositions(),
				this.loadClock()
			]);
		} finally {
			this.refreshing = false;
		}
	}

	/** Refreshes every few seconds while the page is visible and nothing is being submitted. Returns the stop function. */
	startRefreshing(intervalMs = REFRESH_MS): () => void {
		const timer = setInterval(() => {
			if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
			if (this.submitting || this.busy > 0) return;
			void this.refresh();
		}, intervalMs);
		return () => clearInterval(timer);
	}

	/** Assets matching a search, best match first. Not kept in the store: the caller shows them and moves on. */
	async searchAssets(
		search: string,
		assetClass: 'us_equity' | 'crypto' = 'us_equity',
		signal?: AbortSignal
	): Promise<{ assets: Asset[]; total: number } | null> {
		const env = this.env;
		if (!env || !this.usable) return null;
		const envelope = await this.#api.trading(
			env,
			{
				method: 'GET',
				path: '/assets',
				query: { search, asset_class: assetClass, status: 'active', limit: '12' }
			},
			parseAssets,
			{ signal }
		);
		return this.env === env && envelope.status === 'ok' ? envelope.data : null;
	}

	// --- changing things -----------------------------------------------------------------------------------

	#tell(tone: Notice['tone'], text: string): void {
		this.notice = { tone, text, at: Date.now() };
	}

	dismissNotice(): void {
		this.notice = null;
	}

	/** One change, sent once. Says what happened, and on success refreshes whatever it touched. */
	async #act<T>(
		done: string,
		call: TradingCall,
		parse: ((data: unknown) => T) | null,
		refresh: (() => Promise<void>)[] = []
	): Promise<ActionResult<T>> {
		const env = this.env;
		if (!env || !this.usable)
			return { ok: false, envelope: null, error: null, message: 'This environment is not ready.' };
		this.busy++;
		try {
			const envelope = await this.#api.trading(env, call, parse);
			if (this.env !== env)
				return {
					ok: false,
					envelope,
					error: null,
					message: 'The environment changed before the answer arrived.'
				};
			if (envelope.status !== 'ok') {
				const message = envelope.message ?? `Alpaca answered ${envelope.status}.`;
				this.#tell('error', message);
				return { ok: false, envelope, error: null, message };
			}
			this.#tell('success', done);
			await Promise.all(refresh.map((load) => load()));
			return { ok: true, envelope, error: null, message: done };
		} catch (error) {
			const failure = toApiError(error);
			this.#tell('error', failure.message);
			return { ok: false, envelope: null, error: failure, message: failure.message };
		} finally {
			this.busy--;
		}
	}

	#touchedByOrders = () => [this.loadOrders, this.loadPositions, this.loadAccount];

	/**
	 * Places an order. One at a time: a second call while one is out is refused, so a double click cannot place
	 * two. When no answer comes back the order may still exist, so it is looked up by its client ID.
	 */
	async placeOrder(order: Record<string, unknown>): Promise<PlaceResult> {
		const env = this.env;
		if (this.submitting)
			return {
				ok: false,
				envelope: null,
				error: null,
				message: 'An order is already being sent.',
				unknown: null
			};
		if (!env || !this.usable)
			return {
				ok: false,
				envelope: null,
				error: null,
				message: 'This environment is not ready.',
				unknown: null
			};
		this.submitting = true;
		this.busy++;
		try {
			const envelope = await this.#api.trading(
				env,
				{ method: 'POST', path: '/orders', body: order },
				parseOrder
			);
			if (this.env !== env)
				return {
					ok: false,
					envelope,
					error: null,
					message: 'The environment changed before the answer arrived.',
					unknown: null
				};
			if (envelope.status === 'ok') {
				this.#tell(
					'success',
					`Order placed: ${envelope.data?.side ?? ''} ${envelope.data?.symbol ?? ''} (${envelope.data?.status ?? 'sent'}).`
				);
				await Promise.all(this.#touchedByOrders().map((load) => load()));
				return { ok: true, envelope, error: null, message: 'Order placed.', unknown: null };
			}
			if (envelope.outcome_unknown && envelope.client_order_id)
				return await this.#resolve(env, envelope);
			const message = envelope.message ?? `Alpaca answered ${envelope.status}.`;
			this.#tell('error', message);
			return { ok: false, envelope, error: null, message, unknown: null };
		} catch (error) {
			const failure = toApiError(error);
			this.#tell('error', failure.message);
			return {
				ok: false,
				envelope: null,
				error: failure,
				message: failure.message,
				unknown: failure.kind === 'network' || failure.kind === 'timeout' ? 'unclear' : null
			};
		} finally {
			this.submitting = false;
			this.busy--;
		}
	}

	async #resolve(env: string, sent: Envelope<Order>): Promise<PlaceResult> {
		await sleep(LOOKUP_DELAY_MS);
		const id = sent.client_order_id as string;
		try {
			const found = await this.#api.trading(
				env,
				{ method: 'GET', path: `/orders/by-client-id/${encodeURIComponent(id)}` },
				parseOrder
			);
			if (this.env === env && found.status === 'ok') {
				const message =
					'The connection failed, but Alpaca did receive the order. It is in the order list.';
				this.#tell('warning', message);
				await Promise.all(this.#touchedByOrders().map((load) => load()));
				return { ok: true, envelope: found, error: null, message, unknown: 'placed' };
			}
			if (found.status === 'not_found') {
				const message =
					'The connection failed and Alpaca has no order with this ID, so it was not placed. Check the order list before trying again.';
				this.#tell('warning', message);
				return { ok: false, envelope: sent, error: null, message, unknown: 'not_found' };
			}
		} catch {
			// the lookup failed too: fall through to the honest answer
		}
		const message =
			'The connection failed and the order could not be looked up. It may or may not have been placed: check the order list and your positions before trying again.';
		this.#tell('warning', message);
		return { ok: false, envelope: sent, error: null, message, unknown: 'unclear' };
	}

	cancelOrder = (id: string) =>
		this.#act(
			'Order cancelled.',
			{ method: 'DELETE', path: `/orders/${encodeURIComponent(id)}` },
			null,
			this.#touchedByOrders()
		);
	cancelAllOrders = () =>
		this.#act(
			'All open orders were sent a cancel request.',
			{ method: 'DELETE', path: '/orders' },
			parseBulk,
			this.#touchedByOrders()
		);
	replaceOrder = (id: string, changes: Record<string, string>) =>
		this.#act(
			'Order replaced.',
			{ method: 'PATCH', path: `/orders/${encodeURIComponent(id)}`, body: changes },
			parseOrder,
			this.#touchedByOrders()
		);

	closePosition = (symbol: string, how: { qty?: string; percentage?: string } = {}) =>
		this.#act(
			`Closing ${symbol}: an order was placed.`,
			{ method: 'DELETE', path: `/positions/${encodeSymbol(symbol)}`, query: how },
			parseOrder,
			this.#touchedByOrders()
		);
	closeAllPositions = (cancelOrders: boolean) =>
		this.#act(
			'Every position was sent a closing order.',
			{ method: 'DELETE', path: '/positions', query: { cancel_orders: String(cancelOrders) } },
			parseBulk,
			this.#touchedByOrders()
		);
	exercise = (contract: string) =>
		this.#act(
			`Exercise requested for ${contract}.`,
			{ method: 'POST', path: `/positions/${encodeURIComponent(contract)}/exercise` },
			null,
			[this.loadPositions]
		);
	doNotExercise = (contract: string) =>
		this.#act(
			`${contract} will be left to expire.`,
			{ method: 'POST', path: `/positions/${encodeURIComponent(contract)}/do-not-exercise` },
			null,
			[this.loadPositions]
		);

	updateConfig = (changes: Record<string, unknown>) =>
		this.#act(
			'Settings saved.',
			{ method: 'PATCH', path: '/account/configurations', body: changes },
			parseConfig,
			[this.loadConfig, this.loadAccount]
		);

	createWatchlist = (name: string, symbols: string[]) =>
		this.#act(
			`Watchlist ${name} created.`,
			{ method: 'POST', path: '/watchlists', body: { name, symbols } },
			parseWatchlist,
			[this.loadWatchlists]
		);
	renameWatchlist = (id: string, name: string) =>
		this.#act(
			'Watchlist renamed.',
			{ method: 'PUT', path: `/watchlists/${encodeURIComponent(id)}`, body: { name } },
			parseWatchlist,
			[this.loadWatchlists]
		);
	deleteWatchlist = (id: string) =>
		this.#act(
			'Watchlist deleted.',
			{ method: 'DELETE', path: `/watchlists/${encodeURIComponent(id)}` },
			null,
			[this.loadWatchlists]
		);
	addToWatchlist = (id: string, symbol: string) =>
		this.#act(
			`${symbol} added.`,
			{ method: 'POST', path: `/watchlists/${encodeURIComponent(id)}/assets`, body: { symbol } },
			parseWatchlist,
			[this.loadWatchlists]
		);
	removeFromWatchlist = (id: string, symbol: string) =>
		this.#act(
			`${symbol} removed.`,
			{
				method: 'DELETE',
				path: `/watchlists/${encodeURIComponent(id)}/assets/${encodeSymbol(symbol)}`
			},
			parseWatchlist,
			[this.loadWatchlists]
		);
}
