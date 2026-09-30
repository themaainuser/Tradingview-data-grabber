import type { FieldOption, FilterCatalog } from '$lib/filters/catalog';
import { fieldLabel, fieldOptions, isBaseField, makeFieldKey, parseFieldKey } from './fields';
import { generatePresets } from './presets';

/** Filter catalog for time-series bars: raw columns plus every indicator output. */
export function createExplorerCatalog(): FilterCatalog {
	const options: readonly FieldOption[] = fieldOptions();
	return {
		ordered: true,
		options,
		kindOf: (key) => (isBaseField(key) || parseFieldKey(key) ? 'numeric' : null),
		label: fieldLabel,
		params(key) {
			const parsed = parseFieldKey(key);
			if (!parsed || parsed.definition.params.length === 0) return null;
			const { definition, params, output } = parsed;
			return {
				specs: definition.params,
				values: params,
				withParams: (values) => makeFieldKey(definition.id, values, output)
			};
		},
		presets: generatePresets()
	};
}
