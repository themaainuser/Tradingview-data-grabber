import type { ParamSpec } from '$lib/indicators/types';
import type { FilterPreset } from '$lib/explorer/presets';

export interface FieldOption {
	key: string;
	label: string;
	group: string;
	description: string;
	/** Lower-cased text the picker searches. */
	haystack: string;
}

export interface ParamEditing {
	specs: readonly ParamSpec[];
	values: Record<string, number>;
	/** Field key with the given params applied. */
	withParams(values: Record<string, number>): string;
}

/** What the filter builder needs to know about the data it filters. */
export interface FilterCatalog {
	/** Rows are a time series (unlocks crossing / streak operators). */
	ordered: boolean;
	options: readonly FieldOption[];
	kindOf(key: string): 'numeric' | 'text' | null;
	label(key: string): string;
	/** Tunable parameters behind a field, if any. */
	params?(key: string): ParamEditing | null;
	presets?: readonly FilterPreset[];
}
