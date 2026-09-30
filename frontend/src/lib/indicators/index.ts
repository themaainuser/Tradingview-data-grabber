/**
 * Public surface of the indicator library. See `types.ts` for the data model and
 * `registry.ts` for parameter resolution, keys and the catalog.
 */
export type {
	IndicatorCategory,
	IndicatorDefinition,
	IndicatorParams,
	OhlcvColumns,
	OutputSpec,
	ParamSpec,
	SeriesCatalogEntry
} from './types';
export { INDICATOR_CATEGORIES } from './types';
export {
	INDICATORS,
	computeIndicator,
	defaultSeriesCatalog,
	getIndicator,
	indicatorInstanceKey,
	resolveParams,
	seriesKey
} from './registry';
export * as indicatorMath from './math';
