/** Small helpers for drawing the backend's return histogram. Pure functions, unit tested. */

/** Centre of each bin given its n + 1 ascending edges. */
export function binCenters(edges: readonly number[]): number[] {
	return edges.slice(0, -1).map((edge, i) => (edge + edges[i + 1]) / 2);
}

/** Index of the bin containing `value` (the last bin includes its upper edge), or -1 outside all bins. */
export function binIndexOf(edges: readonly number[], value: number): number {
	const last = edges.length - 2;
	if (last < 0 || !(value >= edges[0]) || !(value <= edges[last + 1])) return -1;
	for (let i = 0; i <= last; i++) {
		if (value < edges[i + 1] || i === last) return i;
	}
	return -1;
}

/** Decimals needed to tell neighbouring bin labels apart: finer bins need more. */
export function decimalsFor(step: number): number {
	if (!(step > 0)) return 2;
	if (step < 0.01) return 3;
	if (step < 0.1) return 2;
	return 1;
}

/** A percentage with an explicit sign and a true minus, e.g. "+0.25%" or "\u22120.25%". */
export function formatSignedPct(value: number, decimals = 2): string {
	if (!Number.isFinite(value)) return '\u2014';
	const rounded = Number(value.toFixed(decimals));
	if (rounded === 0) return `${(0).toFixed(decimals)}%`;
	return `${rounded > 0 ? '+' : '\u2212'}${Math.abs(rounded).toFixed(decimals)}%`;
}

/** X-axis labels for a histogram: each bin's centre as a signed percentage. */
export function histogramLabels(edges: readonly number[]): string[] {
	const step = edges.length > 1 ? edges[1] - edges[0] : 0;
	const decimals = decimalsFor(step);
	return binCenters(edges).map((c) => formatSignedPct(c, decimals));
}
