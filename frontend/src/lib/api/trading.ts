/**
 * The trading API's payloads, checked at the boundary like every other backend payload.
 *
 * The backend already turned Alpaca's strings into numbers, so a field is a number, a string or a
 * flag, or `null` when Alpaca did not send it. Each shape below is one table: the name of every
 * field and its kind. A field of the wrong kind raises a contract error instead of drawing a wrong
 * number next to an order button.
 */
import { arr, bool, fail, num, obj, str } from './validate';

type Kind = 'n' | 's' | 'b';
type Spec = Record<string, Kind>;
type Picked<S extends Spec> = {
	[K in keyof S]: S[K] extends 'n'
		? number | null
		: S[K] extends 's'
			? string | null
			: boolean | null;
};

function pick<S extends Spec>(value: unknown, path: string, spec: S): Picked<S> {
	const o = obj(value, path);
	const out: Record<string, unknown> = {};
	for (const [name, kind] of Object.entries(spec)) {
		const v = o[name];
		const where = `${path}.${name}`;
		out[name] =
			v === null || v === undefined
				? null
				: kind === 'n'
					? num(v, where)
					: kind === 's'
						? str(v, where)
						: bool(v, where);
	}
	return out as Picked<S>;
}

const list = <T>(value: unknown, path: string, parse: (item: unknown, path: string) => T): T[] =>
	arr(value, path).map((item, i) => parse(item, `${path}[${i}]`));

// --- the envelope ---------------------------------------------------------------------------------

export type TradingStatus =
	| 'ok'
	| 'not_configured'
	| 'invalid_key'
	| 'rejected'
	| 'not_found'
	| 'rate_limited'
	| 'upstream_error';
export const TRADING_STATUSES: readonly TradingStatus[] = [
	'ok',
	'not_configured',
	'invalid_key',
	'rejected',
	'not_found',
	'rate_limited',
	'upstream_error'
];

/** What every trading call answers: a status and Alpaca's own message, and the data when it worked. */
export interface Envelope<T> {
	environment: string;
	status: TradingStatus;
	message: string | null;
	code: number | null;
	http_status: number | null;
	/** A request that changes something may have reached Alpaca although no answer came back. */
	outcome_unknown: boolean;
	client_order_id: string | null;
	data: T | null;
	fetched_at: number | null;
	elapsed_ms: number;
}

export function parseEnvelope<T>(json: unknown, parse: ((data: unknown) => T) | null): Envelope<T> {
	const o = obj(json, 'response');
	const status = str(o.status, 'status') as TradingStatus;
	if (!TRADING_STATUSES.includes(status)) fail('status', `one of ${TRADING_STATUSES.join(', ')}`);
	const raw = o.data;
	return {
		environment: str(o.environment, 'environment'),
		status,
		message: o.message === null || o.message === undefined ? null : str(o.message, 'message'),
		code: o.code === null || o.code === undefined ? null : num(o.code, 'code'),
		http_status:
			o.http_status === null || o.http_status === undefined
				? null
				: num(o.http_status, 'http_status'),
		outcome_unknown: o.outcome_unknown === true,
		client_order_id:
			o.client_order_id === null || o.client_order_id === undefined
				? null
				: str(o.client_order_id, 'client_order_id'),
		data: status === 'ok' && parse && raw !== null && raw !== undefined ? parse(raw) : null,
		fetched_at:
			o.fetched_at === null || o.fetched_at === undefined ? null : num(o.fetched_at, 'fetched_at'),
		elapsed_ms: num(o.elapsed_ms, 'elapsed_ms')
	};
}

// --- environments -----------------------------------------------------------------------------------

export interface TradingEnvironment {
	id: string;
	label: string;
	real_money: boolean;
	base_url: string;
	enabled: boolean;
	configured: boolean;
	key_env: string;
	secret_env: string;
	fallback_key_env: string | null;
	fallback_secret_env: string | null;
	enable_env: string | null;
	note: string | null;
}

export interface TradingEnvironments {
	default: string;
	environments: TradingEnvironment[];
}

export function parseEnvironments(json: unknown): TradingEnvironments {
	const o = obj(json, 'response');
	const environments = list(o.environments, 'environments', (raw, path): TradingEnvironment => {
		const e = obj(raw, path);
		const optional = (name: string) =>
			e[name] === null || e[name] === undefined ? null : str(e[name], `${path}.${name}`);
		return {
			id: str(e.id, `${path}.id`),
			label: str(e.label, `${path}.label`),
			real_money: bool(e.real_money, `${path}.real_money`),
			base_url: str(e.base_url, `${path}.base_url`),
			enabled: bool(e.enabled, `${path}.enabled`),
			configured: bool(e.configured, `${path}.configured`),
			key_env: str(e.key_env, `${path}.key_env`),
			secret_env: str(e.secret_env, `${path}.secret_env`),
			fallback_key_env: optional('fallback_key_env'),
			fallback_secret_env: optional('fallback_secret_env'),
			enable_env: optional('enable_env'),
			note: optional('note')
		};
	});
	if (new Set(environments.map((e) => e.id)).size !== environments.length)
		fail('environments', 'unique ids');
	return { default: str(o.default, 'default'), environments };
}

// --- the account ------------------------------------------------------------------------------------

const ACCOUNT = {
	id: 's',
	account_number: 's',
	status: 's',
	currency: 's',
	created_at: 's',
	balance_asof: 's',
	crypto_status: 's',
	cash: 'n',
	equity: 'n',
	last_equity: 'n',
	portfolio_value: 'n',
	buying_power: 'n',
	regt_buying_power: 'n',
	non_marginable_buying_power: 'n',
	options_buying_power: 'n',
	sma: 'n',
	initial_margin: 'n',
	maintenance_margin: 'n',
	last_maintenance_margin: 'n',
	multiplier: 'n',
	long_market_value: 'n',
	short_market_value: 'n',
	accrued_fees: 'n',
	pending_transfer_in: 'n',
	pending_transfer_out: 'n',
	pending_reg_taf_fees: 'n',
	intraday_adjustments: 'n',
	options_approved_level: 'n',
	options_trading_level: 'n',
	day_change: 'n',
	day_change_percent: 'n',
	trading_blocked: 'b',
	account_blocked: 'b',
	transfers_blocked: 'b',
	trade_suspended_by_user: 'b',
	shorting_enabled: 'b'
} as const;
export type Account = Picked<typeof ACCOUNT>;
export const parseAccount = (json: unknown): Account => pick(json, 'account', ACCOUNT);

const CONFIG = {
	trade_confirm_email: 's',
	max_margin_multiplier: 's',
	max_options_trading_level: 'n',
	suspend_trade: 'b',
	no_shorting: 'b',
	fractional_trading: 'b',
	disable_overnight_trading: 'b',
	ptp_no_exception_entry: 'b'
} as const;
export type AccountConfig = Picked<typeof CONFIG>;
export const parseConfig = (json: unknown): AccountConfig => pick(json, 'configurations', CONFIG);

export interface PortfolioHistory {
	timeframe: string | null;
	base_value: number | null;
	base_value_asof: string | null;
	timestamp: number[];
	equity: (number | null)[];
	profit_loss: (number | null)[];
	profit_loss_pct: (number | null)[];
}

export function parseHistory(json: unknown): PortfolioHistory {
	const o = obj(json, 'history');
	const timestamp = arr(o.timestamp, 'history.timestamp').map((t, i) =>
		num(t, `history.timestamp[${i}]`)
	);
	const column = (name: string) => {
		const values = arr(o[name], `history.${name}`);
		if (values.length !== timestamp.length)
			fail(`history.${name}`, `an array of ${timestamp.length} values`);
		return values.map((v, i) => (v === null ? null : num(v, `history.${name}[${i}]`)));
	};
	const head = pick(o, 'history', { timeframe: 's', base_value: 'n', base_value_asof: 's' });
	return {
		...head,
		timestamp,
		equity: column('equity'),
		profit_loss: column('profit_loss'),
		profit_loss_pct: column('profit_loss_pct')
	};
}

// --- orders and positions ------------------------------------------------------------------------------

const ORDER = {
	id: 's',
	client_order_id: 's',
	symbol: 's',
	asset_id: 's',
	asset_class: 's',
	side: 's',
	type: 's',
	order_class: 's',
	time_in_force: 's',
	status: 's',
	position_intent: 's',
	created_at: 's',
	submitted_at: 's',
	filled_at: 's',
	canceled_at: 's',
	expired_at: 's',
	failed_at: 's',
	replaced_at: 's',
	expires_at: 's',
	replaced_by: 's',
	replaces: 's',
	qty: 'n',
	notional: 'n',
	filled_qty: 'n',
	filled_avg_price: 'n',
	limit_price: 'n',
	stop_price: 'n',
	trail_price: 'n',
	trail_percent: 'n',
	hwm: 'n',
	ratio_qty: 'n',
	extended_hours: 'b',
	cancelable: 'b',
	open: 'b'
} as const;
export type Order = Picked<typeof ORDER> & { legs: Order[] };

export function parseOrder(json: unknown, path = 'order'): Order {
	const o = obj(json, path);
	return { ...pick(o, path, ORDER), legs: list(o.legs ?? [], `${path}.legs`, parseOrder) };
}
export const parseOrders = (json: unknown): { orders: Order[] } => ({
	orders: list(obj(json, 'orders').orders, 'orders', parseOrder)
});

const POSITION = {
	asset_id: 's',
	symbol: 's',
	asset_class: 's',
	exchange: 's',
	side: 's',
	qty: 'n',
	qty_available: 'n',
	avg_entry_price: 'n',
	cost_basis: 'n',
	current_price: 'n',
	lastday_price: 'n',
	market_value: 'n',
	change_today: 'n',
	unrealized_pl: 'n',
	unrealized_plpc: 'n',
	unrealized_intraday_pl: 'n',
	unrealized_intraday_plpc: 'n',
	asset_marginable: 'b'
} as const;
export type Position = Picked<typeof POSITION>;
export const parsePosition = (json: unknown, path = 'position'): Position =>
	pick(json, path, POSITION);
export const parsePositions = (json: unknown): { positions: Position[] } => ({
	positions: list(obj(json, 'positions').positions, 'positions', parsePosition)
});

export interface BulkResult {
	id?: string | null;
	symbol?: string | null;
	status: number | null;
	ok: boolean;
	message: string | null;
	order: Order | null;
}

export const parseBulk = (json: unknown): { results: BulkResult[] } => ({
	results: list(obj(json, 'bulk').results, 'results', (raw, path): BulkResult => {
		const r = obj(raw, path);
		const text = (name: string) =>
			r[name] === null || r[name] === undefined ? null : str(r[name], `${path}.${name}`);
		return {
			id: text('id'),
			symbol: text('symbol'),
			status: r.status === null || r.status === undefined ? null : num(r.status, `${path}.status`),
			ok: bool(r.ok, `${path}.ok`),
			message: text('message'),
			order: r.order === null || r.order === undefined ? null : parseOrder(r.order, `${path}.order`)
		};
	})
});

// --- assets, contracts, quotes -----------------------------------------------------------------------------

const ASSET = {
	id: 's',
	symbol: 's',
	name: 's',
	class: 's',
	exchange: 's',
	status: 's',
	borrow_status: 's',
	min_order_size: 'n',
	min_trade_increment: 'n',
	price_increment: 'n',
	maintenance_margin_requirement: 'n',
	margin_requirement_long: 'n',
	margin_requirement_short: 'n',
	tradable: 'b',
	marginable: 'b',
	shortable: 'b',
	fractionable: 'b'
} as const;
export type Asset = Picked<typeof ASSET> & { attributes: string[] };
export const parseAsset = (json: unknown, path = 'asset'): Asset => ({
	...pick(json, path, ASSET),
	attributes: list(obj(json, path).attributes ?? [], `${path}.attributes`, (a, p) => str(a, p))
});
export const parseAssets = (json: unknown): { assets: Asset[]; total: number } => {
	const o = obj(json, 'assets');
	return { assets: list(o.assets, 'assets', parseAsset), total: num(o.total, 'total') };
};

const CONTRACT = {
	id: 's',
	symbol: 's',
	name: 's',
	underlying_symbol: 's',
	root_symbol: 's',
	type: 's',
	style: 's',
	status: 's',
	expiration_date: 's',
	open_interest_date: 's',
	close_price_date: 's',
	underlying_asset_id: 's',
	strike_price: 'n',
	multiplier: 'n',
	size: 'n',
	open_interest: 'n',
	close_price: 'n',
	tradable: 'b'
} as const;
export type Contract = Picked<typeof CONTRACT>;
export const parseContract = (json: unknown, path = 'contract'): Contract =>
	pick(json, path, CONTRACT);
export const parseContracts = (
	json: unknown
): { contracts: Contract[]; next_page_token: string | null } => {
	const o = obj(json, 'contracts');
	return {
		contracts: list(o.contracts, 'contracts', parseContract),
		next_page_token:
			o.next_page_token === null || o.next_page_token === undefined
				? null
				: str(o.next_page_token, 'next_page_token')
	};
};

const QUOTE = {
	symbol: 's',
	kind: 's',
	last_time: 's',
	quote_time: 's',
	bid: 'n',
	bid_size: 'n',
	ask: 'n',
	ask_size: 'n',
	mid: 'n',
	spread: 'n',
	last: 'n',
	last_size: 'n',
	open: 'n',
	high: 'n',
	low: 'n',
	close: 'n',
	volume: 'n',
	previous_close: 'n',
	change: 'n',
	change_percent: 'n',
	implied_volatility: 'n'
} as const;
export type Quote = Picked<typeof QUOTE> & { greeks: Record<string, number | null> | null };
export const parseQuote = (json: unknown): Quote => {
	const o = obj(json, 'quote');
	const greeks =
		o.greeks === null || o.greeks === undefined
			? null
			: Object.fromEntries(
					Object.entries(obj(o.greeks, 'quote.greeks')).map(([k, v]) => [
						k,
						v === null ? null : num(v, `quote.greeks.${k}`)
					])
				);
	return { ...pick(o, 'quote', QUOTE), greeks };
};

// --- activity, market, watchlists ---------------------------------------------------------------------------

const ACTIVITY = {
	id: 's',
	activity_type: 's',
	activity_sub_type: 's',
	symbol: 's',
	side: 's',
	order_id: 's',
	order_status: 's',
	type: 's',
	status: 's',
	currency: 's',
	transaction_time: 's',
	created_at: 's',
	date: 's',
	time: 's',
	qty: 'n',
	price: 'n',
	cum_qty: 'n',
	leaves_qty: 'n',
	net_amount: 'n',
	per_share_amount: 'n'
} as const;
export type Activity = Picked<typeof ACTIVITY>;
export const parseActivities = (
	json: unknown
): { activities: Activity[]; next_page_token: string | null } => {
	const o = obj(json, 'activities');
	return {
		activities: list(o.activities, 'activities', (a, p) => pick(a, p, ACTIVITY)),
		next_page_token:
			o.next_page_token === null || o.next_page_token === undefined
				? null
				: str(o.next_page_token, 'next_page_token')
	};
};

const CLOCK = { timestamp: 's', next_open: 's', next_close: 's', is_open: 'b' } as const;
export type Clock = Picked<typeof CLOCK>;
export const parseClock = (json: unknown): Clock => pick(json, 'clock', CLOCK);

const DAY = {
	date: 's',
	open: 's',
	close: 's',
	settlement_date: 's',
	session_open: 's',
	session_close: 's'
} as const;
export type MarketDay = Picked<typeof DAY>;
export const parseCalendar = (json: unknown): { days: MarketDay[] } => ({
	days: list(obj(json, 'calendar').days, 'days', (d, p) => pick(d, p, DAY))
});

export interface Watchlist {
	id: string | null;
	name: string | null;
	created_at: string | null;
	updated_at: string | null;
	assets: Asset[];
}
export const parseWatchlist = (json: unknown, path = 'watchlist'): Watchlist => ({
	...pick(json, path, { id: 's', name: 's', created_at: 's', updated_at: 's' }),
	assets: list(obj(json, path).assets ?? [], `${path}.assets`, parseAsset)
});
export const parseWatchlists = (json: unknown): { watchlists: Watchlist[] } => ({
	watchlists: list(obj(json, 'watchlists').watchlists, 'watchlists', parseWatchlist)
});
