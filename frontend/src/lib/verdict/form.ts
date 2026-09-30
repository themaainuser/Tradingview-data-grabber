/**
 * The Verdict run form: bounds that mirror the backend's validation, so a bad value is caught
 * beside the field instead of as a 422 after the click.
 */
import type { VerdictDefaults, VerdictReport, VerdictRequest } from '$lib/api/contracts';

export const BOUNDS = {
	minTrades: { min: 1, max: 1000 },
	fee: { min: 0, max: 500 },
	spread: { min: 0, max: 1000 },
	slippageK: { min: 0, max: 5 },
	holdoutFraction: { min: 0.1, max: 0.3 }
} as const;

/**
 * Numbers are null while a field is empty (a bound number input reports `undefined` when cleared,
 * which every function here treats the same way); `periodsPerYear` empty means "infer from the bar
 * spacing".
 */
export interface VerdictForm {
	minTrades: number | null | undefined;
	fee: number | null | undefined;
	spread: number | null | undefined;
	slippageK: number | null | undefined;
	periodsPerYear: number | null | undefined;
	holdoutFraction: number;
}

export type FormErrors = Record<keyof VerdictForm, string | null>;

export function formFromDefaults(defaults: VerdictDefaults): VerdictForm {
	return {
		minTrades: defaults.min_trades,
		fee: defaults.costs.fee_bps_per_side,
		spread: defaults.costs.spread_bps,
		slippageK: defaults.costs.slippage_k,
		periodsPerYear: null,
		holdoutFraction: defaults.holdout_fraction
	};
}

function inRange(
	value: number | null | undefined,
	min: number,
	max: number,
	label: string
): string | null {
	if (value === null || value === undefined || !Number.isFinite(value))
		return `${label} is required`;
	if (value < min || value > max) return `${label} must be between ${min} and ${max}`;
	return null;
}

/** `sealed` hides the holdout fraction from validation: it can only be chosen before the first seal. */
export function validateForm(form: VerdictForm, options: { sealed: boolean }): FormErrors {
	const { minTrades, fee, spread, slippageK, holdoutFraction } = BOUNDS;
	let trades = inRange(form.minTrades, minTrades.min, minTrades.max, 'Minimum trades');
	if (!trades && !Number.isInteger(form.minTrades))
		trades = 'Minimum trades must be a whole number';
	let periods: string | null = null;
	const ppy = form.periodsPerYear ?? null;
	if (ppy !== null && !(Number.isFinite(ppy) && ppy > 0)) {
		periods = 'Periods per year must be above 0, or empty to infer it';
	}
	return {
		minTrades: trades,
		fee: inRange(form.fee, fee.min, fee.max, 'Fee'),
		spread: inRange(form.spread, spread.min, spread.max, 'Spread'),
		slippageK: inRange(form.slippageK, slippageK.min, slippageK.max, 'Slippage'),
		periodsPerYear: periods,
		holdoutFraction: options.sealed
			? null
			: inRange(form.holdoutFraction, holdoutFraction.min, holdoutFraction.max, 'Holdout share')
	};
}

export const hasErrors = (errors: FormErrors) => Object.values(errors).some((e) => e !== null);

/** Only call with a form that passed validation. */
export function toRequest(datasetId: string, form: VerdictForm): VerdictRequest {
	return {
		dataset_id: datasetId,
		min_trades: form.minTrades as number,
		costs: {
			fee_bps_per_side: form.fee as number,
			spread_bps: form.spread as number,
			slippage_k: form.slippageK as number
		},
		periods_per_year: form.periodsPerYear ?? null
	};
}

/** True when the form no longer matches the settings the shown report was produced with. */
export function settingsDiffer(form: VerdictForm, report: VerdictReport): boolean {
	const s = report.settings;
	const ppy = form.periodsPerYear ?? null;
	return (
		form.minTrades !== s.min_trades ||
		form.fee !== s.costs.fee_bps_per_side ||
		form.spread !== s.costs.spread_bps ||
		form.slippageK !== s.costs.slippage_k ||
		(ppy !== null && ppy !== s.periods_per_year) ||
		(ppy === null && !s.periods_per_year_inferred)
	);
}
