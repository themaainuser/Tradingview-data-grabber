/**
 * The order ticket's logic, with no screen in it: what each kind of asset offers, a draft of an order
 * and the exact body that draft becomes.
 *
 * The rules are the ones Alpaca documents, and the backend checks them again before anything is sent.
 * They are here so that a mistake is shown beside its field instead of after a round trip.
 */
import type { Quote } from '$lib/api/trading';

export type AssetKind = 'us_equity' | 'crypto' | 'us_option';
export type Side = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit' | 'trailing_stop';
export type TimeInForce = 'day' | 'gtc' | 'opg' | 'cls' | 'ioc' | 'fok';
export type OrderClass = 'simple' | 'bracket' | 'oto' | 'oco';
export type Intent = 'buy_to_open' | 'buy_to_close' | 'sell_to_open' | 'sell_to_close';

export const ALL_TYPES: readonly OrderType[] = [
	'market',
	'limit',
	'stop',
	'stop_limit',
	'trailing_stop'
];
export const ALL_TIME_IN_FORCE: readonly TimeInForce[] = ['day', 'gtc', 'opg', 'cls', 'ioc', 'fok'];
export const KIND_NAMES: Record<AssetKind, string> = {
	us_equity: 'Stock or ETF',
	us_option: 'Option',
	crypto: 'Crypto'
};

export const TYPES: Record<AssetKind, readonly OrderType[]> = {
	us_equity: ALL_TYPES,
	us_option: ['market', 'limit', 'stop', 'stop_limit'],
	crypto: ['market', 'limit', 'stop_limit']
};
export const TIME_IN_FORCE: Record<AssetKind, readonly TimeInForce[]> = {
	us_equity: ALL_TIME_IN_FORCE,
	us_option: ['day', 'gtc'],
	crypto: ['gtc', 'ioc']
};
export const CLASSES: Record<AssetKind, readonly OrderClass[]> = {
	us_equity: ['simple', 'bracket', 'oto', 'oco'],
	us_option: ['simple'],
	crypto: ['simple']
};

export const TYPE_LABELS: Record<OrderType, string> = {
	market: 'Market',
	limit: 'Limit',
	stop: 'Stop',
	stop_limit: 'Stop limit',
	trailing_stop: 'Trailing stop'
};
export const TIME_IN_FORCE_LABELS: Record<TimeInForce, string> = {
	day: 'Day',
	gtc: 'Good till cancelled',
	opg: 'At the open',
	cls: 'At the close',
	ioc: 'Immediate or cancel',
	fok: 'Fill or kill'
};
export const CLASS_LABELS: Record<OrderClass, string> = {
	simple: 'Single order',
	bracket: 'Bracket (take profit and stop loss)',
	oto: 'One triggers other',
	oco: 'One cancels other'
};
export const INTENT_LABELS: Record<Intent, string> = {
	buy_to_open: 'Buy to open',
	buy_to_close: 'Buy to close',
	sell_to_open: 'Sell to open',
	sell_to_close: 'Sell to close'
};

const OPTION_SYMBOL = /^[A-Z0-9.]{1,6}\d{6}[CP]\d{8}$/;
const SYMBOL = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,31}$/;
const POSITIVE = /^(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/;
const SIGNED = /^-?(?:\d+(?:\.\d{0,9})?|\.\d{1,9})$/;

/** The kind of asset a symbol is: a pair with a slash is crypto, an OCC contract symbol an option. */
export function kindOf(symbol: string): AssetKind {
	const s = symbol.trim().toUpperCase();
	if (s.includes('/')) return 'crypto';
	return OPTION_SYMBOL.test(s) ? 'us_option' : 'us_equity';
}

export interface LegDraft {
	symbol: string;
	side: Side;
	ratio: string;
	intent: '' | Intent;
}

export interface OrderDraft {
	symbol: string;
	side: Side;
	type: OrderType;
	timeInForce: TimeInForce;
	sizeBy: 'qty' | 'notional';
	qty: string;
	notional: string;
	limitPrice: string;
	stopPrice: string;
	trailBy: 'price' | 'percent';
	trail: string;
	extendedHours: boolean;
	orderClass: OrderClass;
	takeProfit: string;
	stopLoss: string;
	stopLossLimit: string;
	intent: '' | Intent;
	multiLeg: boolean;
	legs: LegDraft[];
}

export const emptyLeg = (): LegDraft => ({ symbol: '', side: 'buy', ratio: '1', intent: '' });

export const emptyDraft = (symbol = ''): OrderDraft => ({
	symbol,
	side: 'buy',
	type: 'market',
	timeInForce: 'day',
	sizeBy: 'qty',
	qty: '',
	notional: '',
	limitPrice: '',
	stopPrice: '',
	trailBy: 'percent',
	trail: '',
	extendedHours: false,
	orderClass: 'simple',
	takeProfit: '',
	stopLoss: '',
	stopLossLimit: '',
	intent: '',
	multiLeg: false,
	legs: [emptyLeg(), emptyLeg()]
});

/**
 * The draft with every choice put right for its asset: a type, time in force or class that the kind
 * of asset does not offer falls back to the first it does, and fields that only one kind of asset uses are cleared.
 */
export function normalize(draft: OrderDraft): OrderDraft {
	if (draft.multiLeg) {
		return {
			...draft,
			sizeBy: 'qty',
			orderClass: 'simple',
			type: draft.type === 'market' ? 'market' : 'limit',
			timeInForce: draft.timeInForce === 'gtc' ? 'gtc' : 'day',
			extendedHours: false
		};
	}
	const kind = kindOf(draft.symbol);
	const type = TYPES[kind].includes(draft.type) ? draft.type : 'market';
	let timeInForce = TIME_IN_FORCE[kind].includes(draft.timeInForce)
		? draft.timeInForce
		: TIME_IN_FORCE[kind][0];
	if (['opg', 'cls', 'ioc', 'fok'].includes(timeInForce) && type !== 'market' && type !== 'limit')
		timeInForce = 'day';
	const sizeBy =
		draft.sizeBy === 'notional' && kind !== 'us_option' && type === 'market' ? 'notional' : 'qty';
	if (sizeBy === 'notional' && kind === 'us_equity') timeInForce = 'day';
	return {
		...draft,
		type,
		timeInForce,
		sizeBy,
		orderClass: CLASSES[kind].includes(draft.orderClass) ? draft.orderClass : 'simple',
		extendedHours:
			draft.extendedHours && type === 'limit' && (timeInForce === 'day' || timeInForce === 'gtc'),
		intent: kind === 'us_option' ? draft.intent : ''
	};
}

export interface Built {
	/** The body for the backend, or `null` while there are errors. */
	order: Record<string, unknown> | null;
	/** One sentence per field that is wrong, keyed by the field's name in the draft. */
	errors: Record<string, string>;
}

const text = (value: string) => value.trim();

/** The body a draft becomes, or what is wrong with it. Numbers stay exactly as typed. */
export function buildOrder(input: OrderDraft, clientOrderId?: string): Built {
	const draft = normalize(input);
	const errors: Record<string, string> = {};
	const order: Record<string, unknown> = {};
	const positive = (
		field: keyof OrderDraft & string,
		label: string,
		value: string,
		whole = false
	): string | null => {
		const v = text(value);
		if (!v) {
			errors[field] = `${label} is required.`;
			return null;
		}
		if (!POSITIVE.test(v) || Number(v) <= 0) {
			errors[field] = `${label} must be a number greater than zero.`;
			return null;
		}
		if (whole && !Number.isInteger(Number(v))) {
			errors[field] = `${label} must be a whole number.`;
			return null;
		}
		return v;
	};

	if (draft.multiLeg) buildMultiLeg(draft, order, errors, positive);
	else buildSingle(draft, order, errors, positive);
	if (clientOrderId) order.client_order_id = clientOrderId;
	return Object.keys(errors).length > 0 ? { order: null, errors } : { order, errors };
}

type Positive = (
	field: keyof OrderDraft & string,
	label: string,
	value: string,
	whole?: boolean
) => string | null;

function buildSingle(
	draft: OrderDraft,
	order: Record<string, unknown>,
	errors: Record<string, string>,
	positive: Positive
): void {
	const symbol = text(draft.symbol).toUpperCase();
	if (!SYMBOL.test(symbol))
		errors.symbol = 'Enter a symbol such as AAPL, BTC/USD or AAPL260116C00250000.';
	const kind = kindOf(symbol);
	Object.assign(order, {
		symbol,
		side: draft.side,
		type: draft.type,
		time_in_force: draft.timeInForce
	});

	const quantity =
		draft.sizeBy === 'notional'
			? positive('notional', 'The dollar amount', draft.notional)
			: positive(
					'qty',
					kind === 'us_option' ? 'The number of contracts' : 'The quantity',
					draft.qty,
					kind === 'us_option'
				);
	if (quantity !== null) order[draft.sizeBy] = quantity;
	if (
		draft.sizeBy === 'qty' &&
		quantity !== null &&
		kind === 'us_equity' &&
		!Number.isInteger(Number(quantity))
	) {
		if (draft.timeInForce !== 'day')
			errors.timeInForce = 'A fractional quantity needs time in force Day.';
		if (draft.type === 'trailing_stop') errors.qty = 'A trailing stop cannot be fractional.';
	}

	if (draft.type === 'limit' || draft.type === 'stop_limit') {
		const price = positive('limitPrice', 'The limit price', draft.limitPrice);
		if (price !== null) order.limit_price = price;
	}
	if (draft.type === 'stop' || draft.type === 'stop_limit') {
		const price = positive('stopPrice', 'The stop price', draft.stopPrice);
		if (price !== null) order.stop_price = price;
	}
	if (draft.type === 'trailing_stop') {
		const trail = positive(
			'trail',
			draft.trailBy === 'price' ? 'The trail amount' : 'The trail percent',
			draft.trail
		);
		if (trail !== null) order[draft.trailBy === 'price' ? 'trail_price' : 'trail_percent'] = trail;
	}
	if (draft.extendedHours) order.extended_hours = true;

	if (kind === 'us_option' && draft.intent) {
		if (!draft.intent.startsWith(draft.side))
			errors.intent = `${INTENT_LABELS[draft.intent]} does not match ${draft.side}.`;
		else order.position_intent = draft.intent;
	}

	if (draft.orderClass === 'simple') return;
	order.order_class = draft.orderClass;
	if (draft.orderClass === 'oco' && draft.type !== 'limit')
		errors.type = 'A one-cancels-other order is a limit order that exits a position.';
	if (
		(draft.orderClass === 'bracket' || draft.orderClass === 'oto') &&
		draft.type !== 'market' &&
		draft.type !== 'limit'
	) {
		errors.type = `The entry of a ${draft.orderClass === 'bracket' ? 'bracket' : 'one-triggers-other'} order must be a market or limit order.`;
	}
	const wantsTakeProfit = draft.orderClass !== 'oto' || text(draft.takeProfit) !== '';
	const wantsStopLoss = draft.orderClass !== 'oto' || text(draft.stopLoss) !== '';
	if (draft.orderClass === 'oto' && wantsTakeProfit === wantsStopLoss) {
		errors.takeProfit = 'Fill in either take profit or stop loss, not both and not neither.';
		return;
	}
	if (wantsTakeProfit) {
		const price = positive('takeProfit', 'The take-profit price', draft.takeProfit);
		if (price !== null) order.take_profit = { limit_price: price };
	}
	if (wantsStopLoss) {
		const stop = positive('stopLoss', 'The stop-loss price', draft.stopLoss);
		let limit: string | null = null;
		if (text(draft.stopLossLimit))
			limit = positive('stopLossLimit', 'The stop-loss limit price', draft.stopLossLimit);
		if (stop !== null)
			order.stop_loss = { stop_price: stop, ...(limit ? { limit_price: limit } : {}) };
	}
}

function buildMultiLeg(
	draft: OrderDraft,
	order: Record<string, unknown>,
	errors: Record<string, string>,
	positive: Positive
): void {
	Object.assign(order, { order_class: 'mleg', type: draft.type, time_in_force: draft.timeInForce });
	const qty = positive('qty', 'The number of strategies', draft.qty, true);
	if (qty !== null) order.qty = qty;
	if (draft.type === 'limit') {
		const price = text(draft.limitPrice);
		if (!price)
			errors.limitPrice = 'The net price is required: positive for a debit, negative for a credit.';
		else if (!SIGNED.test(price)) errors.limitPrice = 'The net price must be a number.';
		else order.limit_price = price;
	}
	const legs = draft.legs.filter((leg) => text(leg.symbol) !== '');
	if (legs.length < 2 || legs.length > 4) {
		errors.legs = 'A multi-leg order needs two to four legs.';
		return;
	}
	const seen = new Set<string>();
	const built = legs.map((leg, i) => {
		const symbol = text(leg.symbol).toUpperCase();
		const where = `Leg ${i + 1}: `;
		const ratio = text(leg.ratio);
		if (!OPTION_SYMBOL.test(symbol))
			errors.legs ??= `${where}use an option contract symbol such as AAPL260116C00250000.`;
		else if (seen.has(symbol))
			errors.legs ??= `${where}${symbol} appears twice; use the ratio for more of one contract.`;
		else if (!/^\d+$/.test(ratio) || Number(ratio) < 1)
			errors.legs ??= `${where}the ratio must be a whole number from 1.`;
		else if (leg.intent && !leg.intent.startsWith(leg.side))
			errors.legs ??= `${where}${INTENT_LABELS[leg.intent]} does not match ${leg.side}.`;
		seen.add(symbol);
		return {
			symbol,
			ratio_qty: ratio,
			side: leg.side,
			...(leg.intent ? { position_intent: leg.intent } : {})
		};
	});
	order.legs = built;
}

// --- reading an order back ---------------------------------------------------------------------------------

const money = (value: number) =>
	value.toLocaleString('en-US', {
		style: 'currency',
		currency: 'USD',
		maximumFractionDigits: 4,
		minimumFractionDigits: 2
	});

/** One line that says what an order will do, for the review step and the audit of what was sent. */
export function describeOrder(order: Record<string, unknown>): string {
	const str = (name: string) => (typeof order[name] === 'string' ? (order[name] as string) : null);
	const tif =
		TIME_IN_FORCE_LABELS[(str('time_in_force') ?? 'day') as TimeInForce] ?? str('time_in_force');
	if (str('order_class') === 'mleg') {
		const legs = (order.legs as { symbol: string; side: string; ratio_qty: string }[])
			.map((l) => `${l.side} ${l.ratio_qty}× ${l.symbol}`)
			.join(', ');
		const net = str('limit_price');
		const price =
			net === null
				? 'at market'
				: Number(net) < 0
					? `for a credit of ${money(Math.abs(Number(net)))}`
					: `for a debit of ${money(Number(net))}`;
		return `${str('qty')} × multi-leg: ${legs} ${price} · ${tif}`;
	}
	const size = str('qty') ? `${str('qty')}` : `${money(Number(str('notional')))} of`;
	const type = str('type');
	let price = 'at market';
	if (type === 'limit') price = `at a limit of ${money(Number(str('limit_price')))}`;
	else if (type === 'stop') price = `when the price reaches ${money(Number(str('stop_price')))}`;
	else if (type === 'stop_limit')
		price = `with stop ${money(Number(str('stop_price')))} and limit ${money(Number(str('limit_price')))}`;
	else if (type === 'trailing_stop')
		price = str('trail_price')
			? `trailing by ${money(Number(str('trail_price')))}`
			: `trailing by ${str('trail_percent')}%`;
	const side = str('side') === 'sell' ? 'Sell' : 'Buy';
	const extra = [
		order.extended_hours ? 'extended hours' : null,
		str('order_class') && str('order_class') !== 'simple' ? `${str('order_class')} exits` : null
	].filter(Boolean);
	return `${side} ${size} ${str('symbol')} ${price} · ${tif}${extra.length ? ` · ${extra.join(' · ')}` : ''}`;
}

export interface Estimate {
	amount: number | null;
	/** What the amount is based on, in words. */
	basis: string;
}

/**
 * What the order is worth at the price it would most likely get, for the review step. A guess made from
 * the quote and labelled as one: a market order fills at whatever the market gives.
 */
export function estimate(draft: OrderDraft, quote: Quote | null): Estimate {
	const d = normalize(draft);
	if (d.multiLeg) return { amount: null, basis: 'A multi-leg order is priced by its net price.' };
	const multiplier = kindOf(d.symbol) === 'us_option' ? 100 : 1;
	const number = (value: string) => (POSITIVE.test(text(value)) ? Number(text(value)) : null);
	if (d.sizeBy === 'notional') {
		const amount = number(d.notional);
		return { amount, basis: 'The dollar amount you entered.' };
	}
	const qty = number(d.qty);
	if (qty === null) return { amount: null, basis: 'Enter a quantity to see an estimate.' };
	let price: number | null = null;
	let basis = '';
	if (d.type === 'limit' || d.type === 'stop_limit')
		[price, basis] = [number(d.limitPrice), 'at your limit price'];
	else if (d.type === 'stop') [price, basis] = [number(d.stopPrice), 'at your stop price'];
	else if (d.type === 'market') {
		price = (d.side === 'buy' ? quote?.ask : quote?.bid) ?? quote?.last ?? null;
		basis =
			price !== null && quote && (d.side === 'buy' ? quote.ask : quote.bid) !== null
				? `at the current ${d.side === 'buy' ? 'ask' : 'bid'}`
				: 'at the last price';
	}
	if (price === null) return { amount: null, basis: 'No price to estimate from yet.' };
	return { amount: qty * price * multiplier, basis };
}
