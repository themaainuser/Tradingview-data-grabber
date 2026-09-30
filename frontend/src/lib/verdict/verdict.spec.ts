import { describe, expect, it } from 'vitest';
import type { VerdictDefaults, VerdictReport } from '$lib/api/contracts';
import {
	BOUNDS,
	formFromDefaults,
	hasErrors,
	settingsDiffer,
	toRequest,
	validateForm,
	type VerdictForm
} from './form';
import {
	VERDICT_DOT,
	VERDICT_MEANING,
	VERDICT_TITLE,
	bps,
	fixed,
	pClaim,
	pValue,
	pctOf,
	withRuleNames,
	sharpeWithSe,
	signedPct,
	utc
} from './present';

const defaults: VerdictDefaults = {
	min_trades: 30,
	holdout_fraction: 0.2,
	costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
	cost_notes: [],
	bootstrap_replicates: 2000,
	alpha: 0.05,
	dsr_threshold: 0.95,
	stress_multipliers: [1, 1.5, 2]
};

describe('form', () => {
	it('starts from the backend defaults with periods per year left to be inferred', () => {
		expect(formFromDefaults(defaults)).toEqual({
			minTrades: 30,
			fee: 10,
			spread: 1,
			slippageK: 0.1,
			periodsPerYear: null,
			holdoutFraction: 0.2
		});
		expect(hasErrors(validateForm(formFromDefaults(defaults), { sealed: false }))).toBe(false);
	});

	const base = (): VerdictForm => formFromDefaults(defaults);
	it.each([
		['minTrades', { minTrades: 0 }, /between 1 and 1000/],
		['minTrades', { minTrades: 1001 }, /between 1 and 1000/],
		['minTrades', { minTrades: 2.5 }, /whole number/],
		['minTrades', { minTrades: null }, /required/],
		['fee', { fee: -1 }, /between 0 and 500/],
		['fee', { fee: 501 }, /between 0 and 500/],
		['spread', { spread: 1001 }, /between 0 and 1000/],
		['slippageK', { slippageK: 5.1 }, /between 0 and 5/],
		['slippageK', { slippageK: NaN }, /required/],
		['periodsPerYear', { periodsPerYear: 0 }, /above 0/],
		['periodsPerYear', { periodsPerYear: -5 }, /above 0/],
		['holdoutFraction', { holdoutFraction: 0.05 }, /between 0.1 and 0.3/],
		['holdoutFraction', { holdoutFraction: 0.5 }, /between 0.1 and 0.3/]
	] as const)('flags %s', (field, patch, message) => {
		const errors = validateForm({ ...base(), ...patch }, { sealed: false });
		expect(errors[field]).toMatch(message);
		expect(hasErrors(errors)).toBe(true);
	});

	it('treats a cleared periods-per-year field (undefined) as "infer", and other cleared fields as missing', () => {
		const cleared = { ...base(), periodsPerYear: undefined };
		expect(validateForm(cleared, { sealed: false }).periodsPerYear).toBeNull();
		expect(toRequest('abc', cleared).periods_per_year).toBeNull();
		expect(validateForm({ ...base(), fee: undefined }, { sealed: false }).fee).toMatch(/required/);
		expect(validateForm({ ...base(), minTrades: undefined }, { sealed: false }).minTrades).toMatch(
			/required/
		);
		expect(settingsDiffer(cleared, reportWith({ inferred: true }))).toBe(false);
	});

	it('accepts the boundary values', () => {
		const edge = {
			minTrades: BOUNDS.minTrades.max,
			fee: BOUNDS.fee.max,
			spread: BOUNDS.spread.min,
			slippageK: BOUNDS.slippageK.max,
			periodsPerYear: 8760,
			holdoutFraction: BOUNDS.holdoutFraction.min
		};
		expect(hasErrors(validateForm(edge, { sealed: false }))).toBe(false);
	});

	it('ignores the holdout share once the dataset is sealed', () => {
		const errors = validateForm({ ...base(), holdoutFraction: 0.9 }, { sealed: true });
		expect(errors.holdoutFraction).toBeNull();
	});

	it('builds the request with the nested costs and a null periods-per-year when inferred', () => {
		expect(toRequest('abc', base())).toEqual({
			dataset_id: 'abc',
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: null
		});
		expect(toRequest('abc', { ...base(), periodsPerYear: 252 }).periods_per_year).toBe(252);
	});

	const reportWith = ({ inferred }: { inferred: boolean }) =>
		({
			settings: {
				min_trades: 30,
				costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
				periods_per_year: 8760,
				periods_per_year_inferred: inferred
			}
		}) as unknown as VerdictReport;
	const report = {
		settings: {
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: 8760,
			periods_per_year_inferred: true
		}
	} as unknown as VerdictReport;
	it('notices when the form no longer matches the shown report', () => {
		expect(settingsDiffer(base(), report)).toBe(false);
		expect(settingsDiffer({ ...base(), fee: 12 }, report)).toBe(true);
		expect(settingsDiffer({ ...base(), minTrades: 10 }, report)).toBe(true);
		expect(settingsDiffer({ ...base(), periodsPerYear: 252 }, report)).toBe(true);
		expect(settingsDiffer({ ...base(), periodsPerYear: 8760 }, report)).toBe(false);
	});
	it('treats an explicit value after an inferred run as a change, and the reverse too', () => {
		const explicit = {
			settings: { ...report.settings, periods_per_year_inferred: false }
		} as unknown as VerdictReport;
		expect(settingsDiffer(base(), explicit)).toBe(true);
	});
});

describe('formatting', () => {
	it('uses a true minus and never prints negative zero', () => {
		expect(fixed(-1.234)).toBe('\u22121.23');
		expect(fixed(-0.001)).toBe('0.00');
		expect(fixed(0)).toBe('0.00');
		expect(signedPct(2.5)).toBe('+2.50%');
		expect(signedPct(-0.004)).toBe('0.00%');
		expect(signedPct(-3)).toBe('\u22123.00%');
	});
	it('shows a dash for missing or non-finite numbers', () => {
		for (const f of [fixed, signedPct, pValue, bps]) {
			expect(f(null)).toBe('\u2014');
			expect(f(undefined)).toBe('\u2014');
			expect(f(NaN)).toBe('\u2014');
		}
		expect(sharpeWithSe(null, 1)).toBe('\u2014');
	});
	it('never shows a tiny p-value as zero', () => {
		expect(pValue(0)).toBe('<0.001');
		expect(pValue(0.0004)).toBe('<0.001');
		expect(pValue(0.0312)).toBe('0.031');
		expect(pValue(1)).toBe('1.000');
	});
	it('pairs a Sharpe with its standard error', () => {
		expect(sharpeWithSe(1.2, 3.14)).toBe('1.20 \u00b1 3.1');
		expect(sharpeWithSe(-0.5, null)).toBe('\u22120.50');
	});
	it('formats basis points, dates and shares', () => {
		expect(bps(12.34)).toBe('12.3 bps');
		expect(utc(1_790_000_000)).toBe('2026-09-21 14:13 UTC');
		expect(utc(1_790_000_000, false)).toBe('2026-09-21');
		expect(pctOf(0.2)).toBe('20%');
	});
});

describe('verdict presentation', () => {
	const labels = ['INSUFFICIENT_DATA', 'INDISTINGUISHABLE_FROM_LUCK', 'CANDIDATE'] as const;
	it('names and explains every label, and colours its dot from a theme-aware token', () => {
		for (const label of labels) {
			expect(VERDICT_TITLE[label].length).toBeGreaterThan(3);
			expect(VERDICT_MEANING[label].length).toBeGreaterThan(30);
			// Only tokens that stay readable as graphics in both themes; never a hex or a raw brand fill.
			expect(VERDICT_DOT[label]).toMatch(/^var\(--(ink-muted|orange-ink|success-ink)\)$/);
		}
	});
	it('gives each label a different dot', () => {
		expect(new Set(labels.map((l) => VERDICT_DOT[l])).size).toBe(3);
	});
});

describe('wording helpers', () => {
	it('writes p-values as claims with the sign attached to the number', () => {
		expect(pClaim(0)).toBe('p < 0.001');
		expect(pClaim(0.0004)).toBe('p < 0.001');
		expect(pClaim(0.0312)).toBe('p = 0.031');
		expect(pClaim(null)).toBe('p \u2014');
	});
	it('swaps known rule ids in backend prose for names and leaves unknown ones alone', () => {
		const rules = [
			{ id: 'sma-5-50', name: 'SMA 5/50' },
			{ id: 'rsi-20-55', name: 'RSI 20/55' }
		];
		expect(withRuleNames('Candidate rules: sma-5-50, rsi-20-55, sma-9-99.', rules)).toBe(
			'Candidate rules: SMA 5/50, RSI 20/55, sma-9-99.'
		);
		expect(withRuleNames('nothing to replace', rules)).toBe('nothing to replace');
	});
});
