/** Wording and number formatting for the Verdict page. Colours are tokens only (see layout.css). */
import type { RuleStatus, VerdictLabel, VerdictRule } from '$lib/api/contracts';
import { MISSING } from '$lib/format';

export const VERDICT_TITLE: Record<VerdictLabel, string> = {
	INSUFFICIENT_DATA: 'Insufficient data',
	INDISTINGUISHABLE_FROM_LUCK: 'Indistinguishable from luck',
	CANDIDATE: 'Candidate'
};

/** What the label means in one sentence, shown under the headline. */
export const VERDICT_MEANING: Record<VerdictLabel, string> = {
	INSUFFICIENT_DATA:
		'No rule traded often enough for any statistic to mean something, so nothing is ranked and no winner is named.',
	INDISTINGUISHABLE_FROM_LUCK:
		'Some rules traded enough to test, but their results do not stand out from what trying many rules produces by chance, or they do not survive higher costs.',
	CANDIDATE:
		'At least one rule passed every check. It is eligible for one look at the sealed holdout, which is a sanity check and not proof.'
};

/**
 * Dot colour per verdict. Text stays in ink so contrast never depends on the accent, and the dots
 * use the `*-ink` tokens because the vivid brand fills fall below 3:1 as graphics on light surfaces.
 */
export const VERDICT_DOT: Record<VerdictLabel, string> = {
	INSUFFICIENT_DATA: 'var(--ink-muted)',
	INDISTINGUISHABLE_FROM_LUCK: 'var(--orange-ink)',
	CANDIDATE: 'var(--success-ink)'
};

export const STATUS_TITLE: Record<RuleStatus, string> = {
	NEVER_TRADES: 'Never trades',
	INSUFFICIENT_TRADES: 'Too few trades',
	PASSED_GATE: 'Passed gate',
	ERROR: 'Error'
};

const dash = (v: number | null | undefined): v is null | undefined =>
	v === null || v === undefined || !Number.isFinite(v);

/** Fixed decimals with a true minus sign; a dash for missing values. */
export function fixed(value: number | null | undefined, digits = 2): string {
	if (dash(value)) return MISSING;
	const text = Math.abs(value).toFixed(digits);
	return value < 0 && Number(text) !== 0 ? `\u2212${text}` : text;
}

export function signedPct(value: number | null | undefined, digits = 2): string {
	if (dash(value)) return MISSING;
	const text = Math.abs(value).toFixed(digits);
	if (Number(text) === 0) return `${(0).toFixed(digits)}%`;
	return `${value > 0 ? '+' : '\u2212'}${text}%`;
}

/** p-values: three decimals, "<0.001" below that so a tiny value is never shown as zero. */
export function pValue(value: number | null | undefined): string {
	if (dash(value)) return MISSING;
	return value < 0.001 ? '<0.001' : value.toFixed(3);
}

/** A Sharpe estimate with its standard error, e.g. "1.20 \u00b1 3.10". */
export function sharpeWithSe(sharpe: number | null, se: number | null): string {
	if (dash(sharpe)) return MISSING;
	return dash(se) ? fixed(sharpe) : `${fixed(sharpe)} \u00b1 ${fixed(se, 1)}`;
}

export function bps(value: number | null | undefined): string {
	return dash(value) ? MISSING : `${value.toFixed(1)} bps`;
}

export function count(n: number): string {
	return n.toLocaleString('en-US');
}

/** UTC date and time, the app-wide convention. */
export function utc(seconds: number, withTime = true): string {
	const iso = new Date(seconds * 1000).toISOString();
	return withTime ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : iso.slice(0, 10);
}

export const pctOf = (fraction: number) => `${Math.round(fraction * 100)}%`;

/** Why a rule was not tested, in plain words; null for rules that passed the gate. */
export function statusNote(rule: VerdictRule, minTrades: number): string | null {
	switch (rule.status) {
		case 'NEVER_TRADES':
			return 'Never entered a trade, so there is nothing to test.';
		case 'INSUFFICIENT_TRADES':
			return `${count(rule.trades)} ${rule.trades === 1 ? 'trade' : 'trades'} is below the minimum of ${count(minTrades)}: too few for any statistic to mean something.`;
		case 'ERROR':
			return rule.error ?? 'Evaluation failed.';
		default:
			return null;
	}
}

/** "p < 0.001" or "p = 0.031": the comparison sign belongs to the number, never "p = <0.001". */
export function pClaim(value: number | null | undefined): string {
	if (dash(value)) return `p ${MISSING}`;
	return value < 0.001 ? 'p < 0.001' : `p = ${value.toFixed(3)}`;
}

/** Replaces known rule ids in backend prose ("sma-5-50") with their names ("SMA 5/50"). */
export function withRuleNames(
	text: string,
	rules: readonly { id: string; name: string }[]
): string {
	const names = new Map(rules.map((r) => [r.id, r.name]));
	return text.replace(/\b(?:sma|rsi)-\d+-\d+\b/g, (id) => names.get(id) ?? id);
}
