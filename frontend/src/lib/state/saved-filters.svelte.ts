import { nodeId, normalizeTree } from '$lib/filters/tree';
import type { FilterGroup } from '$lib/filters/types';

export interface SavedFilter {
	id: string;
	name: string;
	tree: FilterGroup;
}

function browserStorage(): Storage | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

/**
 * Named filters a researcher saved for reuse, persisted per scope in localStorage.
 * They are user-authored only; the list starts empty. Stored JSON is treated as untrusted and
 * re-validated on load, and storage failures (private mode, quota) degrade to in-memory only.
 */
export class SavedFilters {
	items = $state.raw<SavedFilter[]>([]);
	persistError = $state<string | null>(null);

	readonly #key: string;
	readonly #storage: Storage | null;

	constructor(scope: string, storage: Storage | null = browserStorage()) {
		this.#key = `qr:filters:${scope}`;
		this.#storage = storage;
		this.items = this.#read();
	}

	#read(): SavedFilter[] {
		try {
			const raw = this.#storage?.getItem(this.#key);
			if (!raw) return [];
			const parsed: unknown = JSON.parse(raw);
			if (!Array.isArray(parsed)) return [];
			return parsed.flatMap((entry): SavedFilter[] => {
				if (typeof entry !== 'object' || entry === null) return [];
				const { id, name, tree } = entry as Record<string, unknown>;
				if (typeof name !== 'string' || !name.trim()) return [];
				return [
					{ id: typeof id === 'string' ? id : nodeId(), name, tree: normalizeTree(tree).tree }
				];
			});
		} catch {
			return [];
		}
	}

	#write(items: SavedFilter[]): void {
		this.items = items;
		try {
			this.#storage?.setItem(this.#key, JSON.stringify(items));
			this.persistError = null;
		} catch {
			this.persistError =
				'Could not persist saved filters in this browser; they will be lost on reload.';
		}
	}

	/** Saves a snapshot; an existing filter with the same name is replaced. */
	save(name: string, tree: FilterGroup): SavedFilter | null {
		const trimmed = name.trim();
		if (!trimmed) return null;
		const entry: SavedFilter = { id: nodeId(), name: trimmed, tree: structuredClone(tree) };
		this.#write([...this.items.filter((f) => f.name !== trimmed), entry]);
		return entry;
	}

	remove(id: string): void {
		this.#write(this.items.filter((f) => f.id !== id));
	}
}
