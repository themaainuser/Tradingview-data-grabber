/**
 * Field keys for the bar explorer.
 *
 * A field is either a raw price column (`close`) or one output of a parameterised indicator
 * (`rsi(period=14).value`). Keys are plain strings so filter conditions stay serialisable; this
 * module translates them to and from structured form and to human labels.
 */
import {
	defaultSeriesCatalog,
	getIndicator,
	resolveParams,
	seriesKey,
	type IndicatorDefinition
} from '$lib/indicators';
import type { FieldOption } from '$lib/filters/catalog';

export const BASE_FIELDS = [
	{ key: 'open', label: 'Open' },
	{ key: 'high', label: 'High' },
	{ key: 'low', label: 'Low' },
	{ key: 'close', label: 'Close' },
	{ key: 'volume', label: 'Volume' }
] as const;

export type BaseField = (typeof BASE_FIELDS)[number]['key'];

const BASE_KEYS = new Set<string>(BASE_FIELDS.map((f) => f.key));

export const isBaseField = (key: string): key is BaseField => BASE_KEYS.has(key);

export interface ParsedField {
	definition: IndicatorDefinition;
	params: Record<string, number>;
	output: string;
}

const KEY_PATTERN = /^([a-z0-9_]+)\((.*)\)\.([A-Za-z0-9_]+)$/;

/** Parses an indicator field key; null for base fields and anything unrecognised. */
export function parseFieldKey(key: string): ParsedField | null {
	const match = KEY_PATTERN.exec(key);
	if (!match) return null;
	const definition = getIndicator(match[1]);
	if (!definition || !definition.outputs.some((o) => o.key === match[3])) return null;
	const raw: Record<string, number> = {};
	if (match[2].trim() !== '') {
		for (const pair of match[2].split(',')) {
			const [name, value] = pair.split('=');
			raw[name.trim()] = Number(value);
		}
	}
	const params = resolveParams(definition, raw);
	// Reject keys whose canonical form differs (unknown params, out-of-range values): they would
	// silently evaluate something other than what the condition says.
	return seriesKey(definition.id, params, match[3]) === key
		? { definition, params, output: match[3] }
		: null;
}

export function makeFieldKey(id: string, params: Record<string, number>, output: string): string {
	const definition = getIndicator(id);
	if (!definition) throw new Error(`Unknown indicator: ${id}`);
	return seriesKey(id, resolveParams(definition, params), output);
}

export function isKnownField(key: string): boolean {
	return isBaseField(key) || parseFieldKey(key) !== null;
}

/** "RSI(14)", "MACD(12, 26, 9) signal", "Close". */
export function fieldLabel(key: string): string {
	if (isBaseField(key)) return BASE_FIELDS.find((f) => f.key === key)!.label;
	const parsed = parseFieldKey(key);
	if (!parsed) return key;
	const { definition, params, output } = parsed;
	const args = definition.params.map((p) => params[p.key]).join(', ');
	const head = args ? `${definition.short}(${args})` : definition.short;
	if (definition.outputs.length === 1) return head;
	return `${head} ${definition.outputs.find((o) => o.key === output)!.label}`;
}

let cached: FieldOption[] | null = null;

/** Every selectable field at default parameters: raw columns first, then all indicator outputs. */
export function fieldOptions(): FieldOption[] {
	if (cached) return cached;
	const options: FieldOption[] = BASE_FIELDS.map((f) => ({
		key: f.key,
		label: f.label,
		group: 'Price & volume',
		description: `Raw ${f.label.toLowerCase()} of each bar.`,
		haystack: `${f.label} ${f.key}`.toLowerCase()
	}));
	for (const entry of defaultSeriesCatalog()) {
		const definition = getIndicator(entry.id)!;
		options.push({
			key: entry.key,
			label: fieldLabel(entry.key),
			group: entry.category,
			description: definition.description,
			haystack: `${entry.name} ${definition.short} ${entry.outputLabel} ${entry.id}`.toLowerCase()
		});
	}
	cached = options;
	return options;
}
