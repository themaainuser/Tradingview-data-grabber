import type { OhlcvColumns, OutputSpec, ParamSpec } from './types';

export const int = (
	key: string,
	label: string,
	def: number,
	min: number,
	max: number
): ParamSpec => ({ key, label, default: def, min, max, step: 1, integer: true });

export const num = (
	key: string,
	label: string,
	def: number,
	min: number,
	max: number,
	step: number
): ParamSpec => ({ key, label, default: def, min, max, step });

export const output = (key: string, label: string): OutputSpec => ({ key, label });

export const periodParam = (def = 14, min = 1, max = 500): ParamSpec =>
	int('period', 'Period', def, min, max);

export const windowParam = (def = 20, min = 2, max = 500): ParamSpec =>
	int('window', 'Window', def, min, max);

export const periodsPerYearParam = (): ParamSpec =>
	int('periodsPerYear', 'Periods per year', 252, 1, 525_600);

export const multParam = (def = 2, min = 0.1, max = 10): ParamSpec =>
	num('mult', 'Multiplier', def, min, max, 0.1);

export const VALUE: readonly OutputSpec[] = Object.freeze([
	Object.freeze(output('value', 'Value'))
]);

export function typicalPrice(d: OhlcvColumns): Float64Array {
	const out = new Float64Array(d.close.length);
	for (let i = 0; i < out.length; i++) out[i] = (d.high[i] + d.low[i] + d.close[i]) / 3;
	return out;
}

export function medianPrice(d: OhlcvColumns): Float64Array {
	const out = new Float64Array(d.close.length);
	for (let i = 0; i < out.length; i++) out[i] = (d.high[i] + d.low[i]) / 2;
	return out;
}

export function barRange(d: OhlcvColumns): Float64Array {
	const out = new Float64Array(d.close.length);
	for (let i = 0; i < out.length; i++) out[i] = d.high[i] - d.low[i];
	return out;
}

/** Applies a per-bar estimator that needs open, high, low and close. */
export function perBar(
	d: OhlcvColumns,
	fn: (o: number, h: number, l: number, c: number) => number
): Float64Array {
	const out = new Float64Array(d.close.length);
	for (let i = 0; i < out.length; i++) out[i] = fn(d.open[i], d.high[i], d.low[i], d.close[i]);
	return out;
}
