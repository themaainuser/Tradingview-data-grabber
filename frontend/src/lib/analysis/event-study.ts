/**
 * Conditional forward returns for a filter: "when this condition held, what happened next?"
 *
 * Returns are measured from the close of the matching bar to the close `h` bars later, so they
 * are outcomes of the condition, never inputs to it. Matches within `h` bars of each other
 * overlap, which overstates statistical confidence; `onsetOnly` de-clusters by keeping only the
 * first bar of each run, and the t-statistic is reported with that caveat in the UI.
 */

export interface HorizonStats {
	horizon: number;
	/** Matching bars with a known forward return. */
	n: number;
	hitRate: number | null;
	mean: number | null;
	median: number | null;
	std: number | null;
	best: number | null;
	worst: number | null;
	/** Mean over every bar with a known forward return, regardless of the filter. */
	baselineMean: number | null;
	excessMean: number | null;
	tStat: number | null;
}

export interface EventStudy {
	/** Matching bars (after onset reduction), including those too recent for a forward return. */
	events: number;
	horizons: HorizonStats[];
}

/** 1 only on the first bar of each consecutive run of matches. */
export function onsetMask(mask: Uint8Array): Uint8Array {
	const out = new Uint8Array(mask.length);
	for (let i = 0; i < mask.length; i++)
		out[i] = mask[i] === 1 && (i === 0 || mask[i - 1] === 0) ? 1 : 0;
	return out;
}

function median(sorted: Float64Array): number {
	const mid = sorted.length >> 1;
	return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function eventStudy(
	close: Float64Array,
	mask: Uint8Array | null,
	horizons: readonly number[],
	options: { onsetOnly?: boolean } = {}
): EventStudy {
	const n = close.length;
	const active = mask ? (options.onsetOnly ? onsetMask(mask) : mask) : null;
	let events = 0;
	if (active) for (let i = 0; i < n; i++) events += active[i];

	const stats = horizons.map((horizon): HorizonStats => {
		const returns = new Float64Array(active ? events : 0);
		let count = 0;
		let baselineSum = 0;
		let baselineCount = 0;
		for (let i = 0; i + horizon < n; i++) {
			const r = close[i + horizon] / close[i] - 1;
			if (!Number.isFinite(r)) continue;
			baselineSum += r;
			baselineCount++;
			if (active && active[i] === 1) returns[count++] = r;
		}
		const baselineMean = baselineCount ? baselineSum / baselineCount : null;
		if (!active || count === 0) {
			return {
				horizon,
				n: 0,
				hitRate: null,
				mean: null,
				median: null,
				std: null,
				best: null,
				worst: null,
				baselineMean,
				excessMean: null,
				tStat: null
			};
		}
		const sample = returns.subarray(0, count);
		let sum = 0;
		let wins = 0;
		for (const r of sample) {
			sum += r;
			if (r > 0) wins++;
		}
		const mean = sum / count;
		let squares = 0;
		for (const r of sample) squares += (r - mean) ** 2;
		const std = count > 1 ? Math.sqrt(squares / (count - 1)) : null;
		const sorted = sample.slice().sort();
		return {
			horizon,
			n: count,
			hitRate: wins / count,
			mean,
			median: median(sorted),
			std,
			best: sorted[sorted.length - 1],
			worst: sorted[0],
			baselineMean,
			excessMean: baselineMean === null ? null : mean - baselineMean,
			tStat: std ? mean / (std / Math.sqrt(count)) : null
		};
	});
	return { events, horizons: stats };
}
