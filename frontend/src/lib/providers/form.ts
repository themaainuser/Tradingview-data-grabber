/**
 * Pure logic for the Providers page: parameter validation (the same rules the backend enforces, so
 * a mistake is caught beside the field instead of as a 422), form seeding from the documentation's
 * examples, and the endpoint filters.
 */
import type {
	CatalogCategory,
	CatalogEndpoint,
	CatalogParam,
	ParamValue,
	ParamValues,
	ProviderPlan
} from '$lib/api/providers';

export type Access = 'all' | 'free' | 'premium';

const LONG_TEXT = new Set(['SYMBOLS', 'symbols', 'tickers', 'topics', 'CALCULATIONS', 'keywords']);

/** The parameters a person fills in: everything except the ones the server sets. */
export const visibleParams = (endpoint: CatalogEndpoint): CatalogParam[] =>
	endpoint.params.filter((p) => !p.managed);

/**
 * A parameter's description and its premium note as separate texts. Documentation often states the
 * premium restriction inside the description; it is shown once, highlighted, not twice.
 */
export function describeParam(param: CatalogParam): { text: string; premium: string | null } {
	const note = param.premium_note?.trim() || null;
	if (!note) return { text: param.description, premium: null };
	const rest = param.description
		.replace(note, '')
		.replace(/\s{2,}/g, ' ')
		.trim();
	return { text: rest, premium: note };
}

/** What one fetch costs, in words: `one request` or `20 requests`. */
export const quotaText = (cost: number): string =>
	cost === 1 ? 'one request' : `${cost} requests`;

/** The words on a premium badge: `Premium · Basic` when the endpoint names its plan. */
export const premiumLabel = (endpoint: Pick<CatalogEndpoint, 'plan'>): string =>
	endpoint.plan ? `Premium · ${endpoint.plan}` : 'Premium';

export interface PlanCount extends ProviderPlan {
	/** Endpoints whose cheapest plan is this one. */
	count: number;
	premium: boolean;
}

/** The provider's plans with how many endpoints each one is the first to include. */
export function planCounts(
	plans: readonly ProviderPlan[],
	endpoints: readonly CatalogEndpoint[]
): PlanCount[] {
	return plans.map((plan, index) => {
		const own = endpoints.filter((e) => e.plan === plan.name);
		return {
			...plan,
			count: own.length,
			premium: own.length > 0 ? own.some((e) => e.premium) : index > 0
		};
	});
}

const asList = (value: ParamValue | undefined): string[] =>
	value === undefined ? [] : Array.isArray(value) ? value : [value];

export const isBlank = (value: ParamValue | undefined): boolean =>
	asList(value).every((v) => v.trim() === '');

function validDate(value: string): boolean {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
	const moment = new Date(`${value}T00:00:00Z`);
	return !Number.isNaN(moment.getTime()) && moment.toISOString().slice(0, 10) === value;
}

function validMonth(value: string): boolean {
	const match = /^(\d{4})-(\d{2})$/.exec(value);
	return !!match && Number(match[2]) >= 1 && Number(match[2]) <= 12;
}

function problem(param: CatalogParam, value: string): string | null {
	const limit = LONG_TEXT.has(param.name) ? 2000 : 200;
	if (value.length > limit) return `${param.name} is too long (limit ${limit} characters)`;
	if (param.multiple) return null; // repeated parameters also accept relative values such as "6month"
	switch (param.type) {
		case 'enum':
			return param.enum.includes(value)
				? null
				: `${param.name} must be one of: ${param.enum.join(', ')}`;
		case 'boolean':
			return value === 'true' || value === 'false' ? null : `${param.name} must be true or false`;
		case 'number':
		case 'integer': {
			const whole = param.type === 'integer';
			const n = Number(value);
			if (value === '' || !Number.isFinite(n) || (whole && !Number.isInteger(n)))
				return `${param.name} must be ${whole ? 'a whole number' : 'a number'}`;
			if (param.minimum !== null && n < param.minimum)
				return `${param.name} must be at least ${param.minimum}`;
			if (param.maximum !== null && n > param.maximum)
				return `${param.name} must be at most ${param.maximum}`;
			return null;
		}
		case 'date':
			return validDate(value) ? null : `${param.name} must be a date in YYYY-MM-DD format`;
		case 'month':
			return validMonth(value) ? null : `${param.name} must be a month in YYYY-MM format`;
		default:
			return null;
	}
}

/** Error text by parameter name; a parameter that is fine has no entry. */
export function validateParams(
	endpoint: CatalogEndpoint,
	values: ParamValues
): Record<string, string> {
	const errors: Record<string, string> = {};
	for (const param of visibleParams(endpoint)) {
		const entries = asList(values[param.name])
			.map((v) => v.trim())
			.filter(Boolean);
		if (entries.length === 0) {
			if (param.required) errors[param.name] = `${param.name} is required`;
			continue;
		}
		for (const entry of entries) {
			const message = problem(param, entry);
			if (message) {
				errors[param.name] = message;
				break;
			}
		}
	}
	return errors;
}

/** What is sent: trimmed values, blanks omitted, a repeated parameter as a list. */
export function buildPayload(endpoint: CatalogEndpoint, values: ParamValues): ParamValues {
	const out: ParamValues = {};
	for (const param of visibleParams(endpoint)) {
		const entries = asList(values[param.name])
			.map((v) => v.trim())
			.filter(Boolean);
		if (entries.length === 0) continue;
		out[param.name] = param.multiple ? entries : entries[0];
	}
	return out;
}

/** Form values from one of the documentation's examples; a repeated parameter keeps a blank slot to type into. */
export function valuesFromExample(endpoint: CatalogEndpoint, example: ParamValues): ParamValues {
	const out: ParamValues = {};
	for (const param of visibleParams(endpoint)) {
		const given = example[param.name];
		if (param.multiple) out[param.name] = given === undefined ? [''] : asList(given);
		else if (given !== undefined) out[param.name] = asList(given)[0] ?? '';
	}
	return out;
}

/** Initial form: the first example from the docs, so the form opens on a request that is known to make sense. */
export function seedValues(endpoint: CatalogEndpoint): ParamValues {
	const first = endpoint.examples[0]?.params ?? {};
	const values = valuesFromExample(endpoint, first);
	for (const param of visibleParams(endpoint)) {
		if (param.multiple && values[param.name] === undefined) values[param.name] = [''];
	}
	return values;
}

export interface Filters {
	search: string;
	category: string;
	access: Access;
}

function textMatches(endpoint: CatalogEndpoint, search: string): boolean {
	const needle = search.trim().toLowerCase();
	if (!needle) return true;
	return [endpoint.id, endpoint.title, endpoint.summary].some((text) =>
		text.toLowerCase().includes(needle)
	);
}

const accessMatches = (endpoint: CatalogEndpoint, access: Access) =>
	access === 'all' || (access === 'premium' ? endpoint.premium : !endpoint.premium);

export function filterEndpoints(
	endpoints: readonly CatalogEndpoint[],
	filters: Filters
): CatalogEndpoint[] {
	return endpoints.filter(
		(e) =>
			textMatches(e, filters.search) &&
			(filters.category === 'all' || e.category === filters.category) &&
			accessMatches(e, filters.access)
	);
}

/** Access counts under the current search and category (so the filter buttons say what they would show). */
export function accessCounts(endpoints: readonly CatalogEndpoint[], filters: Filters) {
	const base = endpoints.filter(
		(e) =>
			textMatches(e, filters.search) &&
			(filters.category === 'all' || e.category === filters.category)
	);
	const premium = base.filter((e) => e.premium).length;
	return { all: base.length, free: base.length - premium, premium };
}

/** Category counts under the current search and access filter. */
export function categoryCounts(
	endpoints: readonly CatalogEndpoint[],
	categories: readonly CatalogCategory[],
	filters: Filters
) {
	const base = endpoints.filter(
		(e) => textMatches(e, filters.search) && accessMatches(e, filters.access)
	);
	return categories.map((category) => {
		const inside = base.filter((e) => e.category === category.id);
		return {
			...category,
			shown: inside.length,
			shownPremium: inside.filter((e) => e.premium).length
		};
	});
}
