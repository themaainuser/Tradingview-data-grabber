/**
 * Column source over one dataset's bars.
 *
 * Raw columns are served directly; indicator outputs are computed on first use and memoised by
 * (indicator, resolved params), so a filter that references RSI(14) and a chart pane showing
 * RSI(14) share one computation, and changing one parameter recomputes only that indicator.
 * The cache is bounded by memory so a long exploration session cannot grow without limit.
 */
import type { ColumnSource } from '$lib/filters/types';
import { computeIndicator, indicatorInstanceKey, getIndicator } from '$lib/indicators';
import type { OhlcvColumns } from '$lib/indicators/types';
import { isBaseField, parseFieldKey } from './fields';

const MAX_CACHE_BYTES = 256 * 1024 * 1024;

interface CacheEntry {
	outputs: Float64Array[];
	bytes: number;
}

export class BarSource implements ColumnSource {
	readonly ordered = true;
	readonly length: number;
	readonly columns: OhlcvColumns;
	#cache = new Map<string, CacheEntry>();
	#bytes = 0;

	constructor(columns: OhlcvColumns) {
		this.columns = columns;
		this.length = columns.close.length;
	}

	text(): null {
		return null;
	}

	numeric(field: string): Float64Array | null {
		if (isBaseField(field)) return this.columns[field];
		const parsed = parseFieldKey(field);
		if (!parsed) return null;
		const outputs = this.indicator(parsed.definition.id, parsed.params);
		const index = parsed.definition.outputs.findIndex((o) => o.key === parsed.output);
		return outputs[index] ?? null;
	}

	/** All outputs of an indicator at fully resolved params, computed at most once. */
	indicator(id: string, params: Record<string, number>): Float64Array[] {
		const definition = getIndicator(id);
		if (!definition) throw new Error(`Unknown indicator: ${id}`);
		const key = indicatorInstanceKey(id, params);
		const hit = this.#cache.get(key);
		if (hit) {
			this.#cache.delete(key);
			this.#cache.set(key, hit);
			return hit.outputs;
		}
		const outputs = computeIndicator(definition, this.columns, params);
		const bytes = outputs.reduce((sum, o) => sum + o.byteLength, 0);
		this.#cache.set(key, { outputs, bytes });
		this.#bytes += bytes;
		// Evict least-recently-used entries, but never the one just computed.
		for (const [oldKey, entry] of this.#cache) {
			if (this.#bytes <= MAX_CACHE_BYTES || oldKey === key) break;
			this.#cache.delete(oldKey);
			this.#bytes -= entry.bytes;
		}
		return outputs;
	}

	get cachedIndicators(): number {
		return this.#cache.size;
	}
}
