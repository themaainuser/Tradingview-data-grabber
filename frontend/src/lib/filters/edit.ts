import { isGroup, newGroup, walk } from './tree';
import type { Condition, FilterGroup, FilterNode } from './types';

export type NodePatch = Partial<Omit<Condition, 'type' | 'id'>> &
	Partial<Pick<FilterGroup, 'mode' | 'negate'>>;

/**
 * Mutation API for a filter tree held in reactive state.
 *
 * UI components never mutate the tree they render; they call these methods, so all writes
 * happen in one place (the store that owns the tree) and components stay pure functions of
 * their props.
 */
export interface FilterEditor {
	patch(id: string, patch: NodePatch): void;
	add(groupId: string, node: FilterNode): void;
	remove(id: string): void;
	replace(tree: FilterGroup): void;
	reset(): void;
}

export function createFilterEditor(
	get: () => FilterGroup,
	set: (tree: FilterGroup) => void
): FilterEditor {
	const find = (id: string): FilterNode | undefined => {
		for (const node of walk(get())) if (node.id === id) return node;
		return undefined;
	};
	return {
		patch(id, patch) {
			const node = find(id);
			if (node) Object.assign(node, patch);
		},
		add(groupId, node) {
			const group = find(groupId);
			if (group && isGroup(group)) group.children.push(node);
		},
		remove(id) {
			for (const node of walk(get())) {
				if (!isGroup(node)) continue;
				const index = node.children.findIndex((child) => child.id === id);
				if (index >= 0) {
					node.children.splice(index, 1);
					return;
				}
			}
		},
		replace: set,
		reset: () => set(newGroup('and'))
	};
}
