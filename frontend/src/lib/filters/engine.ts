/**
 * Vectorised filter evaluation.
 *
 * Every condition is compiled to a Uint8Array mask over the source rows in one tight typed-array
 * loop; groups combine masks with bitwise AND/OR. Leaf masks are cached by a signature of
 * (field, operator, operands), so editing one condition in a large filter recomputes only that
 * leaf. Rows with missing values (NaN) never satisfy a condition, which keeps indicator warm-up
 * bars from leaking into results.
 */
import { getOperator } from './operators';
import { isGroup } from './tree';
import type {
	ColumnSource,
	Condition,
	EvaluationResult,
	FilterGroup,
	FilterIssue,
	FilterNode
} from './types';

const EPSILON = 1e-12;

type Leaf =
	{ kind: 'mask'; mask: Uint8Array } | { kind: 'skip' } | { kind: 'invalid'; message: string };

export function signature(c: Condition): string {
	return [c.field, c.op, c.value, c.value2, c.rhs ?? '', c.text].join('\u0001');
}

function compareMask(
	op: 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq',
	a: Float64Array,
	b: Float64Array | null,
	constant: number
): Uint8Array {
	const n = a.length;
	const out = new Uint8Array(n);
	for (let i = 0; i < n; i++) {
		const x = a[i];
		const y = b ? b[i] : constant;
		let hit: boolean;
		switch (op) {
			case 'gt':
				hit = x > y;
				break;
			case 'gte':
				hit = x >= y;
				break;
			case 'lt':
				hit = x < y;
				break;
			case 'lte':
				hit = x <= y;
				break;
			case 'eq':
				hit = Math.abs(x - y) <= EPSILON * Math.max(1, Math.abs(x), Math.abs(y));
				break;
			default:
				hit =
					x === x && y === y && Math.abs(x - y) > EPSILON * Math.max(1, Math.abs(x), Math.abs(y));
		}
		out[i] = hit ? 1 : 0;
	}
	return out;
}

function crossMask(
	above: boolean,
	a: Float64Array,
	b: Float64Array | null,
	constant: number
): Uint8Array {
	const n = a.length;
	const out = new Uint8Array(n);
	for (let i = 1; i < n; i++) {
		const pa = a[i - 1];
		const pb = b ? b[i - 1] : constant;
		const ca = a[i];
		const cb = b ? b[i] : constant;
		// NaN comparisons are false, so warm-up rows can never register a cross.
		out[i] = (above ? pa <= pb && ca > cb : pa >= pb && ca < cb) ? 1 : 0;
	}
	return out;
}

function streakMask(rising: boolean, a: Float64Array, bars: number): Uint8Array {
	const n = a.length;
	const out = new Uint8Array(n);
	let run = 0;
	for (let i = 1; i < n; i++) {
		run = (rising ? a[i] > a[i - 1] : a[i] < a[i - 1]) ? run + 1 : 0;
		out[i] = run >= bars ? 1 : 0;
	}
	return out;
}

/** Strict N-bar breakout using a monotonic deque: O(n) regardless of N. */
function extremeMask(high: boolean, a: Float64Array, bars: number): Uint8Array {
	const n = a.length;
	const out = new Uint8Array(n);
	const deque = new Int32Array(n);
	let head = 0;
	let tail = 0;
	let validRun = 0;
	for (let i = 0; i < n; i++) {
		const x = a[i];
		if (validRun >= bars && x === x) {
			const reference = a[deque[head]];
			out[i] = (high ? x > reference : x < reference) ? 1 : 0;
		}
		if (x !== x) {
			head = tail = 0;
			validRun = 0;
			continue;
		}
		validRun++;
		while (tail > head && (high ? a[deque[tail - 1]] <= x : a[deque[tail - 1]] >= x)) tail--;
		deque[tail++] = i;
		while (head < tail && deque[head] <= i - bars) head++;
	}
	return out;
}

function quantile(sorted: Float64Array, q: number): number {
	const position = (sorted.length - 1) * q;
	const lower = Math.floor(position);
	const upper = Math.ceil(position);
	return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function percentMask(top: boolean, a: Float64Array, percent: number): Uint8Array {
	const valid = new Float64Array(a.length);
	let count = 0;
	for (let i = 0; i < a.length; i++) if (a[i] === a[i]) valid[count++] = a[i];
	const out = new Uint8Array(a.length);
	if (count === 0) return out;
	const sorted = valid.subarray(0, count).sort();
	const threshold = quantile(sorted, top ? 1 - percent / 100 : percent / 100);
	for (let i = 0; i < a.length; i++) {
		const x = a[i];
		out[i] = (top ? x >= threshold : x <= threshold) ? 1 : 0;
	}
	return out;
}

function textMask(
	op: 'in' | 'not_in' | 'contains' | 'starts_with',
	column: readonly string[],
	text: string
): Uint8Array {
	const out = new Uint8Array(column.length);
	const needle = text.trim().toLowerCase();
	const items = new Set(
		text
			.split(',')
			.map((s) => s.trim().toLowerCase())
			.filter(Boolean)
	);
	for (let i = 0; i < column.length; i++) {
		const value = column[i].toLowerCase();
		let hit: boolean;
		if (op === 'in') hit = items.has(value);
		else if (op === 'not_in') hit = !items.has(value);
		else if (op === 'contains') hit = value.includes(needle);
		else hit = value.startsWith(needle);
		out[i] = hit ? 1 : 0;
	}
	return out;
}

function evaluateCondition(c: Condition, source: ColumnSource): Leaf {
	if (c.field === '') return { kind: 'skip' };
	const spec = getOperator(c.op);
	if (spec.ordered && !source.ordered) {
		return { kind: 'invalid', message: `"${spec.label}" needs time-ordered data` };
	}

	if (spec.family === 'text') {
		const column = source.text(c.field);
		if (!column) return { kind: 'invalid', message: `"${c.field}" is not a text field` };
		if (c.text.trim() === '') return { kind: 'skip' };
		return { kind: 'mask', mask: textMask(c.op as 'in', column, c.text) };
	}

	const a = source.numeric(c.field);
	if (!a) return { kind: 'invalid', message: `Unknown numeric field "${c.field}"` };

	switch (spec.operand) {
		case 'none': {
			const out = new Uint8Array(a.length);
			const wantValid = c.op === 'is_valid';
			for (let i = 0; i < a.length; i++) out[i] = Number.isFinite(a[i]) === wantValid ? 1 : 0;
			return { kind: 'mask', mask: out };
		}
		case 'value': {
			let b: Float64Array | null = null;
			if (c.rhs) {
				b = source.numeric(c.rhs);
				if (!b) return { kind: 'invalid', message: `Unknown numeric field "${c.rhs}"` };
			} else if (!Number.isFinite(c.value)) {
				return { kind: 'skip' };
			}
			if (c.op === 'crosses_above' || c.op === 'crosses_below') {
				return { kind: 'mask', mask: crossMask(c.op === 'crosses_above', a, b, c.value) };
			}
			return { kind: 'mask', mask: compareMask(c.op as 'gt', a, b, c.value) };
		}
		case 'range': {
			if (!Number.isFinite(c.value) || !Number.isFinite(c.value2)) return { kind: 'skip' };
			const lo = Math.min(c.value, c.value2);
			const hi = Math.max(c.value, c.value2);
			const out = new Uint8Array(a.length);
			const inside = c.op === 'between';
			for (let i = 0; i < a.length; i++) {
				const x = a[i];
				out[i] = (inside ? x >= lo && x <= hi : x < lo || x > hi) ? 1 : 0;
			}
			return { kind: 'mask', mask: out };
		}
		case 'count': {
			const bars = Math.floor(c.value);
			if (!Number.isFinite(bars) || bars < 1 || bars > 100_000) {
				return { kind: 'invalid', message: 'Bar count must be a whole number of at least 1' };
			}
			if (c.op === 'rising' || c.op === 'falling') {
				return { kind: 'mask', mask: streakMask(c.op === 'rising', a, bars) };
			}
			return { kind: 'mask', mask: extremeMask(c.op === 'new_high', a, bars) };
		}
		case 'percent': {
			if (!Number.isFinite(c.value) || c.value <= 0 || c.value > 100) {
				return { kind: 'invalid', message: 'Percent must be above 0 and at most 100' };
			}
			return { kind: 'mask', mask: percentMask(c.op === 'top_pct', a, c.value) };
		}
		default:
			return { kind: 'invalid', message: `Unsupported operator ${c.op}` };
	}
}

export interface Evaluator {
	evaluate(tree: FilterNode | null): EvaluationResult;
	/** Drops cached leaf masks (call when the underlying data changed in place). */
	clear(): void;
}

/**
 * Creates an evaluator bound to one source. The leaf cache is a small LRU so a long editing
 * session cannot retain hundreds of megabytes of masks for parameter values no longer in use.
 */
export function createEvaluator(source: ColumnSource, maxCachedLeaves = 96): Evaluator {
	const cache = new Map<string, Uint8Array>();

	function leaf(c: Condition, issues: FilterIssue[]): Uint8Array | null {
		const key = signature(c);
		const hit = cache.get(key);
		if (hit) {
			cache.delete(key);
			cache.set(key, hit);
			return hit;
		}
		const result = evaluateCondition(c, source);
		if (result.kind === 'skip') return null;
		if (result.kind === 'invalid') {
			issues.push({ nodeId: c.id, message: result.message });
			return new Uint8Array(source.length);
		}
		cache.set(key, result.mask);
		if (cache.size > maxCachedLeaves) cache.delete(cache.keys().next().value as string);
		return result.mask;
	}

	function node(n: FilterNode, issues: FilterIssue[]): Uint8Array | null {
		if (!n.enabled) return null;
		if (!isGroup(n)) return leaf(n, issues);
		return group(n, issues);
	}

	function group(g: FilterGroup, issues: FilterIssue[]): Uint8Array | null {
		let combined: Uint8Array | null = null;
		for (const child of g.children) {
			const mask = node(child, issues);
			if (!mask) continue;
			if (!combined) {
				combined = mask.slice();
			} else if (g.mode === 'and') {
				for (let i = 0; i < combined.length; i++) combined[i] &= mask[i];
			} else {
				for (let i = 0; i < combined.length; i++) combined[i] |= mask[i];
			}
		}
		if (combined && g.negate) for (let i = 0; i < combined.length; i++) combined[i] ^= 1;
		return combined;
	}

	return {
		evaluate(tree) {
			const issues: FilterIssue[] = [];
			const mask = tree ? node(tree, issues) : null;
			let matched = source.length;
			if (mask) {
				matched = 0;
				for (let i = 0; i < mask.length; i++) matched += mask[i];
			}
			return { mask, matched, total: source.length, issues };
		},
		clear() {
			cache.clear();
		}
	};
}

/** One-shot convenience for tests and scripts. */
export function evaluateFilter(source: ColumnSource, tree: FilterNode | null): EvaluationResult {
	return createEvaluator(source).evaluate(tree);
}
