import { getOperator, isOperator } from './operators';
import type { Condition, FilterGroup, FilterNode, GroupMode, Operator } from './types';

let sequence = 0;

/** Unique within the page. `crypto.randomUUID` is unavailable on plain-http origins, so avoid it. */
export function nodeId(): string {
	sequence += 1;
	return `n${sequence.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function newCondition(init: Partial<Omit<Condition, 'type' | 'id'>> = {}): Condition {
	return {
		type: 'condition',
		id: nodeId(),
		enabled: true,
		field: '',
		op: 'gt',
		value: 0,
		value2: 0,
		rhs: null,
		text: '',
		...init
	};
}

export function newGroup(mode: GroupMode = 'and', children: FilterNode[] = []): FilterGroup {
	return { type: 'group', id: nodeId(), enabled: true, mode, negate: false, children };
}

export function isGroup(node: FilterNode): node is FilterGroup {
	return node.type === 'group';
}

export function* walk(node: FilterNode): Generator<FilterNode> {
	yield node;
	if (isGroup(node)) for (const child of node.children) yield* walk(child);
}

export function conditions(node: FilterNode): Condition[] {
	return [...walk(node)].filter((n): n is Condition => n.type === 'condition');
}

/** Number of enabled conditions that name a field: what the UI shows as "N filters". */
export function countActive(node: FilterNode): number {
	return conditions(node).filter((c) => c.enabled && c.field !== '').length;
}

/** True when an enabled condition peeks at the whole sample (top / bottom percent). */
export function usesLookahead(node: FilterNode): boolean {
	return conditions(node).some((c) => c.enabled && c.field !== '' && getOperator(c.op).lookahead);
}

/** Deep copy with fresh ids, so a loaded preset never shares ids with the live tree. */
export function cloneWithNewIds<T extends FilterNode>(node: T): T {
	if (isGroup(node)) {
		return { ...node, id: nodeId(), children: node.children.map(cloneWithNewIds) } as T;
	}
	return { ...node, id: nodeId() } as T;
}

function formatNumber(value: number): string {
	return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
}

export function describeCondition(
	c: Condition,
	label: (field: string) => string = (f) => f
): string {
	const spec = getOperator(c.op);
	const field = label(c.field);
	const right = c.rhs ? label(c.rhs) : formatNumber(c.value);
	switch (spec.operand) {
		case 'none':
			return `${field} ${spec.label}`;
		case 'range':
			return `${field} ${spec.label} ${formatNumber(Math.min(c.value, c.value2))} and ${formatNumber(Math.max(c.value, c.value2))}`;
		case 'count':
			return `${field} ${spec.label.replace('N', formatNumber(c.value))}`;
		case 'percent':
			return `${field} ${spec.label.replace('X', formatNumber(c.value))}`;
		case 'text':
			return `${field} ${spec.label} "${c.text}"`;
		default:
			return `${field} ${spec.label} ${right}`;
	}
}

export function describeNode(node: FilterNode, label?: (field: string) => string): string {
	if (!isGroup(node)) return describeCondition(node, label);
	const parts = node.children
		.filter((child) => child.enabled && (isGroup(child) || child.field !== ''))
		.map((child) => describeNode(child, label))
		.filter(Boolean);
	if (parts.length === 0) return '';
	const joined =
		parts.length === 1
			? parts[0]
			: parts.map((p) => `(${p})`).join(node.mode === 'and' ? ' AND ' : ' OR ');
	return node.negate ? `NOT (${joined})` : joined;
}

const finite = (value: unknown, fallback: number): number =>
	typeof value === 'number' && Number.isFinite(value) ? value : fallback;

/**
 * Rebuilds a tree from untrusted JSON (localStorage, imported files). Unknown operators and
 * malformed nodes are dropped rather than trusted; the caller learns how many via `dropped`.
 */
export function normalizeTree(input: unknown): { tree: FilterGroup; dropped: number } {
	let dropped = 0;
	const readNode = (raw: unknown, depth: number): FilterNode | null => {
		if (typeof raw !== 'object' || raw === null || depth > 8) {
			dropped++;
			return null;
		}
		const o = raw as Record<string, unknown>;
		if (o.type === 'group') {
			const children = Array.isArray(o.children)
				? o.children
						.map((child) => readNode(child, depth + 1))
						.filter((n): n is FilterNode => n !== null)
				: [];
			return {
				...newGroup(o.mode === 'or' ? 'or' : 'and', children),
				enabled: o.enabled !== false,
				negate: o.negate === true
			};
		}
		if (o.type === 'condition' && isOperator(o.op) && typeof o.field === 'string') {
			return newCondition({
				enabled: o.enabled !== false,
				field: o.field,
				op: o.op as Operator,
				value: finite(o.value, 0),
				value2: finite(o.value2, 0),
				rhs: typeof o.rhs === 'string' && o.rhs !== '' ? o.rhs : null,
				text: typeof o.text === 'string' ? o.text : ''
			});
		}
		dropped++;
		return null;
	};
	const root = readNode(input, 0);
	if (root && isGroup(root)) return { tree: root, dropped };
	return { tree: newGroup('and'), dropped: root ? dropped + 1 : dropped };
}
