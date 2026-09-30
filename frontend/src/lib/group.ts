/**
 * Small pure helpers for building derived lists. They live in a plain module because the
 * Map/Set instances are throw-away locals, not shared reactive state.
 */

/** Groups items by key, preserving first-seen key order and item order. */
export function groupBy<T>(items: readonly T[], key: (item: T) => string): [string, T[]][] {
	const groups = new Map<string, T[]>();
	for (const item of items) {
		const k = key(item);
		const list = groups.get(k);
		if (list) list.push(item);
		else groups.set(k, [item]);
	}
	return [...groups];
}

/** De-duplicates by identity key, keeping the first occurrence. */
export function uniqueBy<T>(items: readonly T[], key: (item: T) => string): T[] {
	const seen = new Set<string>();
	return items.filter((item) => {
		const k = key(item);
		if (seen.has(k)) return false;
		seen.add(k);
		return true;
	});
}
