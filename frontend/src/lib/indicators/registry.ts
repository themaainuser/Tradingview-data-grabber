import { momentumIndicators } from './momentum';
import { priceIndicators } from './price';
import { statisticsIndicators } from './statistics';
import { trendIndicators } from './trend';
import { INDICATOR_CATEGORIES } from './types';
import type {
	IndicatorDefinition,
	IndicatorParams,
	OhlcvColumns,
	SeriesCatalogEntry
} from './types';
import { volatilityIndicators } from './volatility';
import { volumeIndicators } from './volume';

const categoryRank = new Map<string, number>(INDICATOR_CATEGORIES.map((c, i) => [c, i]));

const compare = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/** Every indicator, ordered by category (declaration order in `INDICATOR_CATEGORIES`) then name. */
export const INDICATORS: readonly IndicatorDefinition[] = Object.freeze(
	[
		...trendIndicators,
		...momentumIndicators,
		...volatilityIndicators,
		...volumeIndicators,
		...statisticsIndicators,
		...priceIndicators
	].sort(
		(a, b) =>
			(categoryRank.get(a.category) ?? 0) - (categoryRank.get(b.category) ?? 0) ||
			compare(a.name, b.name) ||
			compare(a.id, b.id)
	)
);

const byId = new Map(INDICATORS.map((def) => [def.id, def]));

export function getIndicator(id: string): IndicatorDefinition | undefined {
	return byId.get(id);
}

function toNumber(raw: unknown): number {
	if (typeof raw === 'number') return raw;
	if (typeof raw === 'string' && raw.trim() !== '') return Number(raw);
	return NaN;
}

function ownEntry(source: unknown, key: string): unknown {
	if (typeof source !== 'object' || source === null) return undefined;
	return Object.prototype.hasOwnProperty.call(source, key)
		? (source as Record<string, unknown>)[key]
		: undefined;
}

/**
 * Fills defaults and coerces user input into a valid parameter set. Missing or non-numeric values
 * fall back to the default, infinite/out-of-range values are clamped into [min, max], integer
 * params are rounded and unknown keys are dropped. Never throws.
 */
export function resolveParams(
	def: IndicatorDefinition,
	overrides?: Record<string, unknown>
): Record<string, number> {
	const out: Record<string, number> = {};
	for (const spec of def.params) {
		let value = toNumber(ownEntry(overrides, spec.key));
		if (Number.isNaN(value)) value = spec.default;
		value = Math.min(spec.max, Math.max(spec.min, value));
		if (spec.integer) value = Math.min(spec.max, Math.max(spec.min, Math.round(value)));
		out[spec.key] = value;
	}
	return out;
}

/** `-0` prints as `0` so equal parameter sets always produce equal keys. */
const formatNumber = (value: number): string => String(value + 0);

/**
 * Canonical instance key such as `macd(fast=12,signal=9,slow=26)`: parameters are resolved
 * against the definition (defaults filled, clamped) and sorted by name, so equivalent inputs map
 * to one key. Unknown indicator ids keep their finite numeric params, sorted.
 */
export function indicatorInstanceKey(id: string, params?: Record<string, unknown>): string {
	const def = byId.get(id);
	let resolved: Record<string, number>;
	if (def) {
		resolved = resolveParams(def, params);
	} else {
		resolved = {};
		for (const key of Object.keys(params ?? {})) {
			const value = toNumber(ownEntry(params, key));
			if (Number.isFinite(value)) resolved[key] = value;
		}
	}
	const body = Object.keys(resolved)
		.sort()
		.map((key) => `${key}=${formatNumber(resolved[key])}`)
		.join(',');
	return `${id}(${body})`;
}

/** Series key such as `rsi(period=14).value`. */
export function seriesKey(
	id: string,
	params: Record<string, unknown> | undefined,
	outputKey: string
): string {
	return `${indicatorInstanceKey(id, params)}.${outputKey}`;
}

/**
 * Resolves params first, then computes; returns one `Float64Array(n)` per declared output.
 * Any non-finite result (e.g. `Infinity` from an infinite input) is normalised to NaN so callers
 * only ever see finite values or "undefined".
 */
export function computeIndicator(
	def: IndicatorDefinition,
	data: OhlcvColumns,
	overrides?: Record<string, unknown>
): Float64Array[] {
	const out = def.compute(data, resolveParams(def, overrides) as IndicatorParams);
	for (const series of out) {
		for (let i = 0; i < series.length; i++) {
			if (!Number.isFinite(series[i])) series[i] = NaN;
		}
	}
	return out;
}

let catalog: readonly SeriesCatalogEntry[] | undefined;

/** Every output of every indicator at default parameters. */
export function defaultSeriesCatalog(): SeriesCatalogEntry[] {
	catalog ??= Object.freeze(
		INDICATORS.flatMap((def) =>
			def.outputs.map((out) =>
				Object.freeze({
					id: def.id,
					name: def.name,
					category: def.category,
					outputKey: out.key,
					outputLabel: out.label,
					key: seriesKey(def.id, {}, out.key),
					pane: def.pane
				})
			)
		)
	);
	return catalog.slice();
}
