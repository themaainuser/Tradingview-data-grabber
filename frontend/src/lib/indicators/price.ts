import { VALUE, medianPrice, perBar, typicalPrice } from './helpers';
import { closeLocationValue, diff, nanArray, pctDiff } from './math';
import type { Series } from './math';
import type { IndicatorDefinition, OhlcvColumns } from './types';

const single = (
	id: string,
	name: string,
	short: string,
	description: string,
	pane: 'price' | 'separate',
	compute: (d: OhlcvColumns) => Series,
	guides?: readonly number[]
): IndicatorDefinition => ({
	id,
	name,
	short,
	description,
	category: 'Price',
	pane,
	...(guides ? { guides } : {}),
	params: [],
	outputs: VALUE,
	compute: (d) => [compute(d)]
});

/** Candle-shape ratios are undefined (NaN) on zero-range bars. */
const ofRange =
	(numerator: (o: number, h: number, l: number, c: number) => number) => (d: OhlcvColumns) =>
		perBar(d, (o, h, l, c) => (h === l ? NaN : (100 * numerator(o, h, l, c)) / (h - l)));

export const priceIndicators: IndicatorDefinition[] = [
	single(
		'typical_price',
		'Typical Price',
		'HLC/3',
		'Average of high, low and close.',
		'price',
		typicalPrice
	),
	single(
		'median_price',
		'Median Price',
		'HL/2',
		'Midpoint of the bar high and low.',
		'price',
		medianPrice
	),
	single(
		'weighted_close',
		'Weighted Close',
		'HLCC/4',
		'Average of high, low and twice the close, weighting the close.',
		'price',
		(d) => perBar(d, (_o, h, l, c) => (h + l + 2 * c) / 4)
	),
	single('ohlc4', 'OHLC Average', 'OHLC/4', 'Average of open, high, low and close.', 'price', (d) =>
		perBar(d, (o, h, l, c) => (o + h + l + c) / 4)
	),
	single(
		'range_pct',
		'Bar Range %',
		'Range %',
		'High-low range of the bar as a percent of the close.',
		'separate',
		(d) => perBar(d, (_o, h, l, c) => (c === 0 ? NaN : (100 * (h - l)) / c))
	),
	single(
		'body_pct',
		'Candle Body %',
		'Body %',
		'Signed close-minus-open as a percent of the bar range (+100 = full bullish body).',
		'separate',
		ofRange((o, _h, _l, c) => c - o),
		[0]
	),
	single(
		'upper_wick_pct',
		'Upper Wick %',
		'Up wick %',
		'Distance from the high to the top of the body as a percent of the bar range.',
		'separate',
		ofRange((o, h, _l, c) => h - Math.max(o, c))
	),
	single(
		'lower_wick_pct',
		'Lower Wick %',
		'Low wick %',
		'Distance from the bottom of the body to the low as a percent of the bar range.',
		'separate',
		ofRange((o, _h, l, c) => Math.min(o, c) - l)
	),
	single(
		'gap_pct',
		'Gap % vs Previous Close',
		'Gap %',
		'Percent difference between the open and the previous close.',
		'separate',
		(d) => {
			const out = nanArray(d.close.length);
			for (let i = 1; i < out.length; i++) {
				out[i] = d.close[i - 1] === 0 ? NaN : 100 * (d.open[i] / d.close[i - 1] - 1);
			}
			return out;
		},
		[0]
	),
	single(
		'clv',
		'Close Location Value',
		'CLV',
		'Where the close sits in the bar range, from -1 (at the low) to +1 (at the high); 0 on zero-range bars.',
		'separate',
		(d) => closeLocationValue(d.high, d.low, d.close),
		[0]
	),
	single(
		'intraday_return',
		'Intrabar Return %',
		'Open-close %',
		'Percent change from the open to the close of the same bar.',
		'separate',
		(d) => pctDiff(d.close, d.open),
		[0]
	),
	single(
		'price_change',
		'Close Change',
		'ΔClose',
		'Absolute change of the close versus the previous close.',
		'separate',
		(d) => diff(d.close, 1),
		[0]
	)
];
