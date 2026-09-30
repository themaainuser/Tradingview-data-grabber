/**
 * Public contracts of the indicator library.
 *
 * Data is columnar (typed arrays, one entry per bar). Every indicator returns exactly one
 * `Float64Array(n)` per declared output, with `NaN` wherever the value is undefined (warm-up,
 * missing input, zero denominators). A value at bar `i` only ever depends on bars `<= i`.
 */

export interface OhlcvColumns {
	time: Float64Array;
	open: Float64Array;
	high: Float64Array;
	low: Float64Array;
	close: Float64Array;
	volume: Float64Array;
}

export const INDICATOR_CATEGORIES = [
	'Trend',
	'Momentum',
	'Volatility',
	'Volume',
	'Statistics',
	'Price'
] as const;

export type IndicatorCategory = (typeof INDICATOR_CATEGORIES)[number];

export interface ParamSpec {
	key: string;
	label: string;
	default: number;
	min: number;
	max: number;
	step: number;
	integer?: boolean;
}

export interface OutputSpec {
	key: string;
	label: string;
}

export type IndicatorParams = Readonly<Record<string, number>>;

export interface IndicatorDefinition {
	/** Stable snake_case identifier, e.g. `sma`, `rsi`, `bollinger`. */
	id: string;
	name: string;
	short: string;
	/** One sentence stating what the indicator measures. */
	description: string;
	category: IndicatorCategory;
	/** `price`: shares the price scale (overlay). `separate`: needs its own axis. */
	pane: 'price' | 'separate';
	params: readonly ParamSpec[];
	outputs: readonly OutputSpec[];
	/** Reference levels (e.g. RSI 30/70). Only valid for `separate` panes. */
	guides?: readonly number[];
	/** Expects fully resolved params (see `resolveParams`); returns one array per output. */
	compute(data: OhlcvColumns, params: IndicatorParams): Float64Array[];
}

export interface SeriesCatalogEntry {
	id: string;
	name: string;
	category: IndicatorCategory;
	outputKey: string;
	outputLabel: string;
	/** Globally unique series key at default params, e.g. `rsi(period=14).value`. */
	key: string;
	pane: 'price' | 'separate';
}
