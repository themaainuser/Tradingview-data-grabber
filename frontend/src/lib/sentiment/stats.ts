/**
 * Pure range and zone statistics for the Fear & Greed page. Everything here is computed from the
 * readings the backend returned; nothing is estimated, so a range with no data yields empty results.
 */
import type { BandKey, FearGreedBand } from '$lib/api/contracts';

const DAY = 86_400;

export type RangeKey = '30d' | '90d' | '1y' | 'all';

export const RANGES: readonly { key: RangeKey; label: string; days: number | null }[] = [
	{ key: '30d', label: '30D', days: 30 },
	{ key: '90d', label: '90D', days: 90 },
	{ key: '1y', label: '1Y', days: 365 },
	{ key: 'all', label: 'All', days: null }
];

/** Index of the first reading inside the trailing window ending at the last reading; 0 for "all". */
export function rangeStart(time: readonly number[], days: number | null): number {
	if (days === null || time.length === 0) return 0;
	const cutoff = time[time.length - 1] - days * DAY;
	// Times are ascending, so binary search the first index with time >= cutoff.
	let lo = 0;
	let hi = time.length - 1;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if (time[mid] >= cutoff) hi = mid;
		else lo = mid + 1;
	}
	return lo;
}

/** The band a score falls in: lower bound inclusive, upper exclusive, the top band includes its end. */
export function bandOf(score: number, bands: readonly FearGreedBand[]): FearGreedBand | null {
	const last = bands.length - 1;
	for (const [i, band] of bands.entries()) {
		if (score >= band.from && (score < band.to || (i === last && score <= band.to))) return band;
	}
	return null;
}

export interface ZoneShare {
	key: BandKey;
	label: string;
	count: number;
	/** Fraction of readings in the range, 0 to 1. */
	share: number;
}

/** How many readings from `start` onwards fall in each band. Shares sum to 1 when there are readings. */
export function zoneCounts(
	scores: readonly number[],
	start: number,
	bands: readonly FearGreedBand[]
): ZoneShare[] {
	const counts = new Map<BandKey, number>(bands.map((b) => [b.key, 0]));
	let total = 0;
	for (let i = start; i < scores.length; i++) {
		const band = bandOf(scores[i], bands);
		if (!band) continue;
		counts.set(band.key, (counts.get(band.key) ?? 0) + 1);
		total++;
	}
	return bands.map((b) => ({
		key: b.key,
		label: b.label,
		count: counts.get(b.key) ?? 0,
		share: total === 0 ? 0 : (counts.get(b.key) ?? 0) / total
	}));
}

export interface RangeSummary {
	count: number;
	mean: number;
	high: { score: number; time: number };
	low: { score: number; time: number };
	/** Change from the first to the last reading in the range. */
	change: number;
}

/** Mean, extremes and net change over readings from `start`; null when the range is empty. */
export function rangeSummary(
	time: readonly number[],
	scores: readonly number[],
	start: number
): RangeSummary | null {
	const count = scores.length - start;
	if (count <= 0) return null;
	let sum = 0;
	let high = start;
	let low = start;
	for (let i = start; i < scores.length; i++) {
		sum += scores[i];
		// `>=` / `<=` make the latest of several equal extremes win, like the backend's year high/low.
		if (scores[i] >= scores[high]) high = i;
		if (scores[i] <= scores[low]) low = i;
	}
	return {
		count,
		mean: sum / count,
		high: { score: scores[high], time: time[high] },
		low: { score: scores[low], time: time[low] },
		change: scores[scores.length - 1] - scores[start]
	};
}

/** Signed difference formatted for display: "+3", "−5", "0". Uses a true minus sign. */
export function formatDelta(delta: number): string {
	if (delta === 0) return '0';
	return `${delta > 0 ? '+' : '\u2212'}${Math.abs(delta)}`;
}
