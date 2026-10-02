import { describe, expect, it } from 'vitest';
import {
	buildOrder,
	CLASSES,
	describeOrder,
	emptyDraft,
	emptyLeg,
	estimate,
	kindOf,
	normalize,
	TIME_IN_FORCE,
	TYPES,
	type OrderDraft
} from './order';
import type { Quote } from '$lib/api/trading';

const CALL = 'AAPL260116C00250000';
const PUT = 'AAPL260116P00240000';
const draft = (changes: Partial<OrderDraft> = {}): OrderDraft => ({
	...emptyDraft('AAPL'),
	qty: '10',
	...changes
});
const built = (changes: Partial<OrderDraft> = {}, id?: string) => buildOrder(draft(changes), id);
const orderOf = (changes: Partial<OrderDraft> = {}) => {
	const result = built(changes);
	expect(result.errors).toEqual({});
	return result.order;
};
const errorsOf = (changes: Partial<OrderDraft> = {}) => built(changes).errors;

const quote = (over: Partial<Quote> = {}): Quote => ({
	symbol: 'AAPL',
	kind: 'us_equity',
	last_time: null,
	quote_time: null,
	bid: 220.95,
	bid_size: 2,
	ask: 221.05,
	ask_size: 3,
	mid: 221,
	spread: 0.1,
	last: 221,
	last_size: 100,
	open: null,
	high: null,
	low: null,
	close: null,
	volume: null,
	previous_close: null,
	change: null,
	change_percent: null,
	implied_volatility: null,
	greeks: null,
	...over
});

describe('what each kind of asset is', () => {
	it('is told by its symbol', () => {
		expect(
			[
				'AAPL',
				'brk.b',
				'BTC/USD',
				'btc/usd',
				CALL,
				CALL.toLowerCase(),
				'AAPL1260116C00250000',
				'BTCUSD'
			].map(kindOf)
		).toEqual([
			'us_equity',
			'us_equity',
			'crypto',
			'crypto',
			'us_option',
			'us_option',
			'us_option',
			'us_equity'
		]);
	});

	it('offers each kind only what Alpaca documents for it', () => {
		expect(TYPES.us_equity).toEqual(['market', 'limit', 'stop', 'stop_limit', 'trailing_stop']);
		expect(TYPES.us_option).toEqual(['market', 'limit', 'stop', 'stop_limit']);
		expect(TYPES.crypto).toEqual(['market', 'limit', 'stop_limit']);
		expect(TIME_IN_FORCE.us_equity).toEqual(['day', 'gtc', 'opg', 'cls', 'ioc', 'fok']);
		expect(TIME_IN_FORCE.us_option).toEqual(['day', 'gtc']);
		expect(TIME_IN_FORCE.crypto).toEqual(['gtc', 'ioc']);
		expect(CLASSES.us_equity).toEqual(['simple', 'bracket', 'oto', 'oco']);
		expect(CLASSES.us_option).toEqual(['simple']);
		expect(CLASSES.crypto).toEqual(['simple']);
	});
});

describe('normalize', () => {
	it('puts right a choice the asset does not offer', () => {
		expect(
			normalize(
				draft({
					symbol: 'BTC/USD',
					type: 'trailing_stop',
					timeInForce: 'day',
					orderClass: 'bracket'
				})
			)
		).toMatchObject({ type: 'market', timeInForce: 'gtc', orderClass: 'simple' });
		expect(
			normalize(draft({ symbol: CALL, timeInForce: 'ioc', type: 'trailing_stop' }))
		).toMatchObject({ type: 'market', timeInForce: 'day' });
		expect(normalize(draft({ type: 'stop', stopPrice: '1', timeInForce: 'opg' })).timeInForce).toBe(
			'day'
		);
		expect(normalize(draft({ type: 'limit', timeInForce: 'opg' })).timeInForce).toBe('opg');
	});

	it('only keeps a dollar amount for a market order on something that has one, and a day order for stocks', () => {
		expect(normalize(draft({ sizeBy: 'notional', timeInForce: 'gtc' }))).toMatchObject({
			sizeBy: 'notional',
			timeInForce: 'day'
		});
		expect(normalize(draft({ sizeBy: 'notional', type: 'limit' })).sizeBy).toBe('qty');
		expect(normalize(draft({ symbol: CALL, sizeBy: 'notional' })).sizeBy).toBe('qty');
		expect(
			normalize(draft({ symbol: 'ETH/USD', sizeBy: 'notional', timeInForce: 'gtc' }))
		).toMatchObject({ sizeBy: 'notional', timeInForce: 'gtc' });
	});

	it('keeps extended hours only for a day or good-till-cancelled limit order and an intent only for an option', () => {
		expect(normalize(draft({ extendedHours: true })).extendedHours).toBe(false);
		expect(normalize(draft({ extendedHours: true, type: 'limit' })).extendedHours).toBe(true);
		expect(
			normalize(draft({ extendedHours: true, type: 'limit', timeInForce: 'ioc' })).extendedHours
		).toBe(false);
		expect(normalize(draft({ intent: 'buy_to_open' })).intent).toBe('');
		expect(normalize(draft({ symbol: CALL, intent: 'buy_to_open' })).intent).toBe('buy_to_open');
	});

	it('limits a multi-leg order to market or limit, day or good till cancelled', () => {
		expect(
			normalize(
				draft({
					multiLeg: true,
					type: 'stop',
					timeInForce: 'ioc',
					sizeBy: 'notional',
					extendedHours: true
				})
			)
		).toMatchObject({ type: 'limit', timeInForce: 'day', sizeBy: 'qty', extendedHours: false });
		expect(normalize(draft({ multiLeg: true, type: 'market', timeInForce: 'gtc' }))).toMatchObject({
			type: 'market',
			timeInForce: 'gtc'
		});
	});
});

describe('the body an order becomes', () => {
	it('sends a market order exactly as typed, with the symbol in capitals', () => {
		expect(built({ symbol: ' aapl ', qty: '10.50' }, 'my-id').order).toEqual({
			symbol: 'AAPL',
			side: 'buy',
			type: 'market',
			time_in_force: 'day',
			qty: '10.50',
			client_order_id: 'my-id'
		});
		expect(orderOf({ qty: '.5' })).toMatchObject({ qty: '.5' });
	});

	it('carries the prices of each type and none that the type would ignore', () => {
		expect(orderOf({ type: 'limit', limitPrice: '200.25', stopPrice: '9' })).toEqual({
			symbol: 'AAPL',
			side: 'buy',
			type: 'limit',
			time_in_force: 'day',
			qty: '10',
			limit_price: '200.25'
		});
		expect(orderOf({ type: 'stop', stopPrice: '210', limitPrice: '9' })).toMatchObject({
			type: 'stop',
			stop_price: '210'
		});
		expect(orderOf({ type: 'stop', stopPrice: '210' })).not.toHaveProperty('limit_price');
		expect(
			orderOf({ type: 'stop_limit', stopPrice: '210', limitPrice: '209.5', timeInForce: 'gtc' })
		).toMatchObject({ stop_price: '210', limit_price: '209.5', time_in_force: 'gtc' });
		expect(
			orderOf({ side: 'sell', type: 'trailing_stop', trailBy: 'percent', trail: '2.5' })
		).toMatchObject({ trail_percent: '2.5' });
		expect(
			orderOf({ side: 'sell', type: 'trailing_stop', trailBy: 'price', trail: '3' })
		).toMatchObject({ trail_price: '3' });
		expect(
			orderOf({ side: 'sell', type: 'trailing_stop', trailBy: 'price', trail: '3' })
		).not.toHaveProperty('trail_percent');
	});

	it('sends a dollar amount instead of a quantity and the other way round', () => {
		const dollars = orderOf({ sizeBy: 'notional', notional: '500.75', qty: '99' });
		expect(dollars).toMatchObject({ notional: '500.75' });
		expect(dollars).not.toHaveProperty('qty');
		expect(orderOf({ qty: '3', notional: '500' })).not.toHaveProperty('notional');
	});

	it('sends extended hours and an option intent when they apply', () => {
		expect(orderOf({ type: 'limit', limitPrice: '9', extendedHours: true })).toMatchObject({
			extended_hours: true
		});
		expect(orderOf({ symbol: CALL, qty: '2', intent: 'buy_to_open' })).toMatchObject({
			symbol: CALL,
			position_intent: 'buy_to_open',
			qty: '2'
		});
		expect(orderOf({ symbol: 'BTC/USD', qty: '0.01', timeInForce: 'gtc' })).toMatchObject({
			symbol: 'BTC/USD',
			time_in_force: 'gtc'
		});
	});

	it('builds bracket, one-triggers-other and one-cancels-other orders with their exit legs', () => {
		expect(
			orderOf({ orderClass: 'bracket', takeProfit: '240', stopLoss: '200', stopLossLimit: '199.5' })
		).toMatchObject({
			order_class: 'bracket',
			take_profit: { limit_price: '240' },
			stop_loss: { stop_price: '200', limit_price: '199.5' }
		});
		expect(orderOf({ orderClass: 'bracket', takeProfit: '240', stopLoss: '200' })).toMatchObject({
			stop_loss: { stop_price: '200' }
		});
		expect(orderOf({ orderClass: 'oto', stopLoss: '200', takeProfit: '' })).toMatchObject({
			order_class: 'oto',
			stop_loss: { stop_price: '200' }
		});
		expect(orderOf({ orderClass: 'oto', stopLoss: '', takeProfit: '240' })).not.toHaveProperty(
			'stop_loss'
		);
		expect(
			orderOf({
				orderClass: 'oco',
				side: 'sell',
				type: 'limit',
				limitPrice: '240',
				takeProfit: '240',
				stopLoss: '200'
			})
		).toMatchObject({ order_class: 'oco' });
		expect(orderOf({ takeProfit: '240', stopLoss: '200' })).not.toHaveProperty('take_profit'); // a single order ignores exit prices
	});

	it('builds a multi-leg order from its filled legs only', () => {
		const legs = [
			{
				symbol: CALL.toLowerCase(),
				side: 'buy' as const,
				ratio: '1',
				intent: 'buy_to_open' as const
			},
			{ symbol: PUT, side: 'sell' as const, ratio: '2', intent: '' as const },
			emptyLeg()
		];
		expect(
			orderOf({ multiLeg: true, symbol: '', qty: '1', type: 'limit', limitPrice: '-0.35', legs })
		).toEqual({
			order_class: 'mleg',
			type: 'limit',
			time_in_force: 'day',
			qty: '1',
			limit_price: '-0.35',
			legs: [
				{ symbol: CALL, ratio_qty: '1', side: 'buy', position_intent: 'buy_to_open' },
				{ symbol: PUT, ratio_qty: '2', side: 'sell' }
			]
		});
		expect(orderOf({ multiLeg: true, qty: '1', type: 'market', legs })).not.toHaveProperty(
			'limit_price'
		);
	});
});

describe('mistakes are said beside the field', () => {
	it.each([
		[{ symbol: '' }, 'symbol', 'Enter a symbol'],
		[{ symbol: '../account' }, 'symbol', 'Enter a symbol'],
		[{ qty: '' }, 'qty', 'quantity is required'],
		[{ qty: '0' }, 'qty', 'greater than zero'],
		[{ qty: '-3' }, 'qty', 'greater than zero'],
		[{ qty: 'abc' }, 'qty', 'greater than zero'],
		[{ qty: '1e3' }, 'qty', 'greater than zero'],
		[{ qty: '1.5', timeInForce: 'gtc' }, 'timeInForce', 'needs time in force Day'],
		[
			{ qty: '1.5', side: 'sell', type: 'trailing_stop', trail: '1', timeInForce: 'day' },
			'qty',
			'cannot be fractional'
		],
		[{ symbol: CALL, qty: '1.5' }, 'qty', 'whole number'],
		[{ sizeBy: 'notional', notional: '' }, 'notional', 'dollar amount is required'],
		[{ sizeBy: 'notional', notional: '0' }, 'notional', 'greater than zero'],
		[{ type: 'limit' }, 'limitPrice', 'limit price is required'],
		[{ type: 'limit', limitPrice: '-1' }, 'limitPrice', 'greater than zero'],
		[{ type: 'stop' }, 'stopPrice', 'stop price is required'],
		[{ type: 'stop_limit', stopPrice: '1' }, 'limitPrice', 'limit price is required'],
		[{ type: 'trailing_stop' }, 'trail', 'trail percent is required'],
		[{ type: 'trailing_stop', trailBy: 'price' }, 'trail', 'trail amount is required'],
		[{ symbol: CALL, side: 'sell', intent: 'buy_to_open' }, 'intent', 'does not match sell'],
		[{ orderClass: 'bracket' }, 'takeProfit', 'take-profit price is required'],
		[{ orderClass: 'bracket', takeProfit: '9' }, 'stopLoss', 'stop-loss price is required'],
		[
			{ orderClass: 'bracket', takeProfit: '9', stopLoss: '1', stopLossLimit: 'x' },
			'stopLossLimit',
			'greater than zero'
		],
		[
			{ orderClass: 'bracket', type: 'stop', stopPrice: '5', takeProfit: '9', stopLoss: '1' },
			'type',
			'must be a market or limit'
		],
		[{ orderClass: 'oto' }, 'takeProfit', 'either take profit or stop loss'],
		[
			{ orderClass: 'oto', takeProfit: '9', stopLoss: '1' },
			'takeProfit',
			'either take profit or stop loss'
		],
		[{ orderClass: 'oco', takeProfit: '9', stopLoss: '1' }, 'type', 'limit order that exits']
	] as [Partial<OrderDraft>, string, string][])('%j', (changes, field, words) => {
		const errors = errorsOf(changes);
		expect(errors[field], JSON.stringify(errors)).toContain(words);
		expect(built(changes).order).toBeNull();
	});

	it('refuses a multi-leg order that is not two to four distinct option contracts', () => {
		const two = [
			{ symbol: CALL, side: 'buy' as const, ratio: '1', intent: '' as const },
			{ symbol: PUT, side: 'sell' as const, ratio: '1', intent: '' as const }
		];
		const multi = (changes: Partial<OrderDraft>) =>
			errorsOf({ multiLeg: true, qty: '1', type: 'market', legs: two, ...changes });
		expect(multi({})).toEqual({});
		expect(multi({ qty: '1.5' }).qty).toContain('whole number');
		expect(multi({ type: 'limit' }).limitPrice).toContain('net price is required');
		expect(multi({ type: 'limit', limitPrice: 'free' }).limitPrice).toContain('must be a number');
		expect(multi({ legs: [two[0]] }).legs).toContain('two to four legs');
		expect(multi({ legs: [...two, ...two, ...two] }).legs).toContain('two to four legs');
		expect(multi({ legs: [{ ...two[0], symbol: 'AAPL' }, two[1]] }).legs).toContain(
			'Leg 1: use an option contract'
		);
		expect(multi({ legs: [two[0], { ...two[0], side: 'sell' }] }).legs).toContain('appears twice');
		expect(multi({ legs: [{ ...two[0], ratio: '0' }, two[1]] }).legs).toContain(
			'ratio must be a whole number'
		);
		expect(multi({ legs: [two[0], { ...two[1], intent: 'buy_to_open' }] }).legs).toContain(
			'does not match sell'
		);
	});

	it('reports every wrong field at once, not one at a time', () => {
		expect(Object.keys(errorsOf({ symbol: '', qty: '', type: 'limit' })).sort()).toEqual([
			'limitPrice',
			'qty',
			'symbol'
		]);
	});
});

describe('reading an order back', () => {
	it('says what each kind of order will do', () => {
		expect(describeOrder(orderOf()!)).toBe('Buy 10 AAPL at market · Day');
		expect(
			describeOrder(
				orderOf({ side: 'sell', type: 'limit', limitPrice: '225.5', timeInForce: 'gtc' })!
			)
		).toBe('Sell 10 AAPL at a limit of $225.50 · Good till cancelled');
		expect(describeOrder(orderOf({ type: 'stop', stopPrice: '210' })!)).toBe(
			'Buy 10 AAPL when the price reaches $210.00 · Day'
		);
		expect(
			describeOrder(orderOf({ type: 'stop_limit', stopPrice: '210', limitPrice: '209.5' })!)
		).toContain('with stop $210.00 and limit $209.50');
		expect(
			describeOrder(orderOf({ side: 'sell', type: 'trailing_stop', trail: '2.5' })!)
		).toContain('trailing by 2.5%');
		expect(
			describeOrder(orderOf({ side: 'sell', type: 'trailing_stop', trailBy: 'price', trail: '3' })!)
		).toContain('trailing by $3.00');
		expect(describeOrder(orderOf({ sizeBy: 'notional', notional: '500' })!)).toBe(
			'Buy $500.00 of AAPL at market · Day'
		);
		expect(
			describeOrder(
				orderOf({
					type: 'limit',
					limitPrice: '9',
					extendedHours: true,
					orderClass: 'bracket',
					takeProfit: '12',
					stopLoss: '8',
					timeInForce: 'gtc'
				})!
			)
		).toContain('extended hours · bracket exits');
	});

	it('says a multi-leg order is a debit or a credit', () => {
		const legs = [
			{ symbol: CALL, side: 'buy' as const, ratio: '1', intent: '' as const },
			{ symbol: PUT, side: 'sell' as const, ratio: '1', intent: '' as const }
		];
		expect(
			describeOrder(orderOf({ multiLeg: true, qty: '2', type: 'limit', limitPrice: '1.25', legs })!)
		).toBe(`2 × multi-leg: buy 1× ${CALL}, sell 1× ${PUT} for a debit of $1.25 · Day`);
		expect(
			describeOrder(
				orderOf({ multiLeg: true, qty: '1', type: 'limit', limitPrice: '-0.35', legs })!
			)
		).toContain('for a credit of $0.35');
		expect(describeOrder(orderOf({ multiLeg: true, qty: '1', type: 'market', legs })!)).toContain(
			'at market'
		);
	});
});

describe('the estimate', () => {
	it('prices a market order at the ask when buying and the bid when selling', () => {
		expect(estimate(draft(), quote())).toEqual({
			amount: expect.closeTo(2210.5, 6),
			basis: 'at the current ask'
		});
		expect(estimate(draft({ side: 'sell' }), quote())).toEqual({
			amount: expect.closeTo(2209.5, 6),
			basis: 'at the current bid'
		});
		expect(estimate(draft(), quote({ ask: null, bid: null }))).toEqual({
			amount: 2210,
			basis: 'at the last price'
		});
	});

	it('uses the price the order names, and 100 shares per option contract', () => {
		expect(estimate(draft({ type: 'limit', limitPrice: '200' }), null)).toEqual({
			amount: 2000,
			basis: 'at your limit price'
		});
		expect(estimate(draft({ type: 'stop', stopPrice: '210' }), null)).toEqual({
			amount: 2100,
			basis: 'at your stop price'
		});
		expect(
			estimate(draft({ symbol: CALL, qty: '2', type: 'limit', limitPrice: '4.1' }), null).amount
		).toBeCloseTo(820, 6);
	});

	it('says why it has no estimate instead of guessing', () => {
		expect(estimate(draft({ qty: '' }), quote()).amount).toBeNull();
		expect(estimate(draft(), null)).toEqual({
			amount: null,
			basis: 'No price to estimate from yet.'
		});
		expect(estimate(draft({ type: 'trailing_stop', trail: '1' }), quote()).amount).toBeNull();
		expect(estimate(draft({ sizeBy: 'notional', notional: '500' }), null)).toEqual({
			amount: 500,
			basis: 'The dollar amount you entered.'
		});
		expect(estimate(draft({ multiLeg: true }), quote()).amount).toBeNull();
	});
});
