/** Number formatting shared by tables, legends and stat panels. Missing values render as an em dash. */

export const MISSING = '\u2014';

export type NumberFormat = 'pct' | 'ratio' | 'int' | 'number' | 'price' | 'compact';

export function formatValue(value: number | null | undefined, format: NumberFormat): string {
	if (value === null || value === undefined || !Number.isFinite(value)) return MISSING;
	switch (format) {
		case 'pct':
			return `${value.toFixed(2)}%`;
		case 'ratio':
			return value.toFixed(2);
		case 'int':
			return Math.round(value).toLocaleString('en-US');
		case 'price':
			return value.toLocaleString('en-US', {
				minimumFractionDigits: 2,
				maximumFractionDigits: Math.abs(value) < 1 ? 6 : 4
			});
		case 'compact':
			return new Intl.NumberFormat('en-US', {
				notation: 'compact',
				maximumFractionDigits: 2
			}).format(value);
		default:
			return Number(value.toPrecision(6)).toLocaleString('en-US', { maximumFractionDigits: 6 });
	}
}

export function formatBytes(bytes: number): string {
	if (!Number.isFinite(bytes)) return MISSING;
	const units = ['B', 'KB', 'MB', 'GB'];
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit++;
	}
	return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
	if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return MISSING;
	if (seconds < 90) return `${Math.round(seconds)}s`;
	if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
	if (seconds < 172_800) return `${(seconds / 3600).toFixed(1)}h`;
	return `${(seconds / 86_400).toFixed(1)}d`;
}
