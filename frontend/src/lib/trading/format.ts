/** How the trading page writes numbers, signs and times. A missing value is a dash, never a zero. */
export const DASH = '\u2014';

const usd = (digits: number) =>
	new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD',
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	});
const CENTS = usd(2);
const FOUR = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD',
	minimumFractionDigits: 2,
	maximumFractionDigits: 4
});

/** Dollars. Prices keep up to four decimals (sub-penny quotes), totals keep two. */
export function money(value: number | null | undefined, precise = false): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
	return (precise ? FOUR : CENTS).format(value);
}

/** A quantity with up to nine decimals and no trailing zeros: `10`, `0.5`, `0.000171`. */
export function quantity(value: number | null | undefined): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
	return value.toLocaleString('en-US', { maximumFractionDigits: 9 });
}

/** A value already in percent (`1.25` is 1.25%). */
export function percent(value: number | null | undefined, digits = 2): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
	return `${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

/** Alpaca sends some changes as fractions (`0.0124` is 1.24%): this turns them into percent. */
export const fractionToPercent = (value: number | null | undefined): number | null =>
	value === null || value === undefined ? null : value * 100;

/** `+$12.50` / `-$3.00`; zero has no sign. */
export function signedMoney(value: number | null | undefined): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
	return `${value > 0 ? '+' : value < 0 ? '-' : ''}${CENTS.format(Math.abs(value))}`;
}

export function signedPercent(value: number | null | undefined, digits = 2): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
	return `${value > 0 ? '+' : value < 0 ? '-' : ''}${percent(Math.abs(value), digits)}`;
}

/** The colour class for a gain or a loss; nothing for zero or missing. The sign is always written too, so colour is never the only cue. */
export const tone = (value: number | null | undefined): string =>
	value === null || value === undefined || value === 0 || !Number.isFinite(value)
		? ''
		: value > 0
			? 'text-success-ink'
			: 'text-coral-ink';

/** `Sep 30, 2:30 PM` in the viewer's time zone; the original text when it is not a timestamp. */
export function when(iso: string | null | undefined): string {
	if (!iso) return DASH;
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return iso;
	return date.toLocaleString('en-US', {
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});
}

/** How long until `iso`, from `now`: `2h 05m`, `3d 4h`, `now`, or a dash. */
export function timeUntil(iso: string | null | undefined, now: number): string {
	if (!iso) return DASH;
	const target = new Date(iso).getTime();
	if (Number.isNaN(target)) return DASH;
	const minutes = Math.floor((target - now) / 60000);
	if (minutes <= 0) return 'now';
	const days = Math.floor(minutes / 1440);
	const hours = Math.floor((minutes % 1440) / 60);
	if (days > 0) return `${days}d ${hours}h`;
	return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
}

/** `buy_to_open` -> `Buy to open`; `partially_filled` -> `Partially filled`. */
export function words(value: string | null | undefined): string {
	if (!value) return DASH;
	const text = value.replaceAll('_', ' ');
	return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The tone of an order status: done well, still going, or ended without a fill. */
export function statusTone(
	status: string | null | undefined
): 'success' | 'destructive' | 'secondary' | 'default' {
	if (status === 'filled') return 'success';
	if (status === 'rejected' || status === 'canceled' || status === 'expired' || status === 'failed')
		return 'destructive';
	if (status === 'replaced' || status === 'done_for_day') return 'secondary';
	return 'default';
}
