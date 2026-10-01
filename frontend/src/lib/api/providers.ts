/**
 * Types and strict validators for the data-provider endpoints.
 *
 * The backend turns every provider response into a handful of drawable views; this module checks
 * those payloads before they reach a component, so a malformed one raises a contract error instead
 * of drawing wrong numbers. The invariants checked here are the ones the page relies on: a failed
 * query carries a message and no views, and every series column lines up with its time axis.
 */
import { arr, bool, fail, nullableNum, nullableStr, num, obj, str } from './validate';

export type QueryStatus =
	| 'ok'
	| 'empty'
	| 'not_configured'
	| 'rate_limited'
	| 'premium_required'
	| 'invalid_key'
	| 'invalid_request'
	| 'upstream_error';

const STATUSES: readonly QueryStatus[] = [
	'ok',
	'empty',
	'not_configured',
	'rate_limited',
	'premium_required',
	'invalid_key',
	'invalid_request',
	'upstream_error'
];

export type ParamValue = string | string[];
export type ParamValues = Record<string, ParamValue>;

export interface ProviderPlan {
	name: string;
	summary: string;
}

export interface ProviderSummary {
	id: string;
	name: string;
	description: string;
	website: string;
	docs_url: string;
	key_env: string;
	key_url: string | null;
	configured: boolean;
	endpoint_count: number;
	premium_count: number;
	limits_note: string;
	/** Subscription tiers, cheapest first; empty for a provider that only distinguishes free from premium. */
	plans: ProviderPlan[];
	requests_this_session: number;
}

export type ParamType =
	'text' | 'number' | 'integer' | 'date' | 'datetime' | 'month' | 'boolean' | 'enum';

export interface CatalogParam {
	name: string;
	required: boolean;
	type: ParamType;
	description: string;
	/** Strict: the documentation states these are the accepted values. */
	enum: string[];
	enum_labels: Record<string, string>;
	/** Hints only; free text is still allowed. */
	suggestions: string[];
	default: string | null;
	example: string | null;
	multiple: boolean;
	premium_note: string | null;
	/** Bounds of a number or integer; null when the documentation states none. */
	minimum: number | null;
	maximum: number | null;
	/** The choices (a subset of `enum`) that need a paid plan. */
	premium_values: string[];
	/** Set by the server (for example the response format); never shown. */
	managed: boolean;
}

export interface CatalogEndpoint {
	id: string;
	title: string;
	category: string;
	description: string;
	summary: string;
	premium: boolean;
	trending: boolean;
	utility: boolean;
	premium_notes: string[];
	/** The cheapest plan that includes this endpoint; null when the provider has no tiers. */
	plan: string | null;
	/** How many requests one fetch counts against the quota. */
	request_cost: number;
	doc_url: string;
	params: CatalogParam[];
	examples: { caption: string; params: ParamValues }[];
}

export interface CatalogCategory {
	id: string;
	title: string;
	summary: string;
	count: number;
	premium_count: number;
}

export interface Catalog {
	provider: ProviderSummary;
	categories: CatalogCategory[];
	endpoints: CatalogEndpoint[];
}

interface ViewBase {
	id: string;
	title: string;
	subtitle: string | null;
}

export type SeriesRole = 'open' | 'high' | 'low' | 'close' | 'volume' | 'value';

export interface SeriesView extends ViewBase {
	kind: 'series';
	/** UTC epoch seconds, ascending. */
	time: number[];
	intraday: boolean;
	series: {
		key: string;
		label: string;
		values: (number | null)[];
		role: SeriesRole;
		unit: string | null;
	}[];
	time_note: string | null;
	truncated: boolean;
	total_points: number;
}

export type ColumnType = 'text' | 'number' | 'percent' | 'date' | 'datetime' | 'url';
export type Cell = string | number | null;

export interface TableView extends ViewBase {
	kind: 'table';
	columns: { key: string; label: string; type: ColumnType }[];
	rows: Cell[][];
	total_rows: number;
	truncated: boolean;
}

export type FactFormat =
	'text' | 'number' | 'integer' | 'percent' | 'currency' | 'date' | 'url' | 'sentiment';

export interface Fact {
	key: string;
	label: string;
	value: string | number | null;
	format: FactFormat;
	tone: 'positive' | 'negative' | null;
	hint: string | null;
}

export interface FactsView extends ViewBase {
	kind: 'facts';
	groups: { title: string | null; items: Fact[] }[];
}

export interface BarsView extends ViewBase {
	kind: 'bars';
	labels: string[];
	values: (number | null)[];
	format: 'number' | 'percent' | 'currency';
	sign_colors: boolean;
	value_label: string;
}

export interface FeedItem {
	title: string;
	url: string | null;
	source: string | null;
	published: number | null;
	summary: string | null;
	sentiment: { score: number | null; label: string | null } | null;
	tags: string[];
	tickers: {
		symbol: string;
		relevance: number | null;
		score: number | null;
		label: string | null;
	}[];
}

export interface FeedView extends ViewBase {
	kind: 'feed';
	items: FeedItem[];
	total_items: number;
	truncated: boolean;
}

export interface HeatmapView extends ViewBase {
	kind: 'heatmap';
	rows: string[];
	cols: string[];
	values: (number | null)[][];
	scale: 'diverging' | 'sequential';
	domain: [number, number] | null;
}

export interface TextView extends ViewBase {
	kind: 'text';
	blocks: {
		heading: string | null;
		subheading: string | null;
		body: string;
		badge: string | null;
	}[];
	total_blocks: number;
	truncated: boolean;
}

export type ProviderView =
	SeriesView | TableView | FactsView | BarsView | FeedView | HeatmapView | TextView;

export interface QueryResponse {
	provider: string;
	endpoint: string;
	title: string;
	status: QueryStatus;
	message: string | null;
	cached: boolean;
	/** UTC epoch seconds. */
	fetched_at: number | null;
	elapsed_ms: number;
	bytes: number;
	/** What was sent upstream; the API key is never part of it. */
	params: ParamValues;
	views: ProviderView[];
	raw: unknown;
	raw_omitted: { bytes: number; reason: string } | null;
	notes: string[];
}

// ---- validators -----------------------------------------------------------------------------------

const strings = (value: unknown, path: string) =>
	arr(value, path).map((v, i) => str(v, `${path}[${i}]`));

function paramValues(value: unknown, path: string): ParamValues {
	const out: ParamValues = {};
	for (const [key, raw] of Object.entries(obj(value, path))) {
		out[key] = Array.isArray(raw) ? strings(raw, `${path}.${key}`) : str(raw, `${path}.${key}`);
	}
	return out;
}

export function parseProvider(value: unknown, path = 'provider'): ProviderSummary {
	const o = obj(value, path);
	return {
		id: str(o.id, `${path}.id`),
		name: str(o.name, `${path}.name`),
		description: str(o.description, `${path}.description`),
		website: str(o.website, `${path}.website`),
		docs_url: str(o.docs_url, `${path}.docs_url`),
		key_env: str(o.key_env, `${path}.key_env`),
		key_url: nullableStr(o.key_url, `${path}.key_url`),
		configured: bool(o.configured, `${path}.configured`),
		endpoint_count: num(o.endpoint_count, `${path}.endpoint_count`),
		premium_count: num(o.premium_count, `${path}.premium_count`),
		limits_note: str(o.limits_note, `${path}.limits_note`),
		plans: arr(o.plans, `${path}.plans`).map((raw, i) => {
			const plan = obj(raw, `${path}.plans[${i}]`);
			return {
				name: str(plan.name, `${path}.plans[${i}].name`),
				summary: str(plan.summary, `${path}.plans[${i}].summary`)
			};
		}),
		requests_this_session: num(o.requests_this_session, `${path}.requests_this_session`)
	};
}

export function parseProviders(json: unknown): ProviderSummary[] {
	const providers = arr(obj(json, 'response').providers, 'providers').map((p, i) =>
		parseProvider(p, `providers[${i}]`)
	);
	if (new Set(providers.map((p) => p.id)).size !== providers.length)
		fail('providers', 'unique ids');
	return providers;
}

const PARAM_TYPES: readonly ParamType[] = [
	'text',
	'number',
	'integer',
	'date',
	'datetime',
	'month',
	'boolean',
	'enum'
];

function catalogParam(value: unknown, path: string): CatalogParam {
	const o = obj(value, path);
	const type = str(o.type, `${path}.type`);
	if (!PARAM_TYPES.includes(type as ParamType))
		fail(`${path}.type`, `one of ${PARAM_TYPES.join(', ')}`);
	const labels: Record<string, string> = {};
	for (const [key, label] of Object.entries(obj(o.enum_labels ?? {}, `${path}.enum_labels`))) {
		labels[key] = str(label, `${path}.enum_labels.${key}`);
	}
	const choices = strings(o.enum, `${path}.enum`);
	const premiumValues = strings(o.premium_values, `${path}.premium_values`);
	if (!premiumValues.every((v) => choices.includes(v)))
		fail(`${path}.premium_values`, 'a subset of the parameter choices');
	return {
		name: str(o.name, `${path}.name`),
		required: bool(o.required, `${path}.required`),
		type: type as ParamType,
		description: str(o.description, `${path}.description`),
		enum: choices,
		enum_labels: labels,
		suggestions: strings(o.suggestions, `${path}.suggestions`),
		default: nullableStr(o.default, `${path}.default`),
		example: nullableStr(o.example, `${path}.example`),
		multiple: bool(o.multiple, `${path}.multiple`),
		premium_note: nullableStr(o.premium_note, `${path}.premium_note`),
		minimum: nullableNum(o.minimum, `${path}.minimum`),
		maximum: nullableNum(o.maximum, `${path}.maximum`),
		premium_values: premiumValues,
		managed: bool(o.managed, `${path}.managed`)
	};
}

export function parseCatalog(json: unknown): Catalog {
	const o = obj(json, 'catalog');
	const endpoints = arr(o.endpoints, 'endpoints').map((raw, i): CatalogEndpoint => {
		const p = `endpoints[${i}]`;
		const e = obj(raw, p);
		const cost = num(e.request_cost, `${p}.request_cost`);
		if (!Number.isInteger(cost) || cost < 1)
			fail(`${p}.request_cost`, 'a whole number of at least 1');
		return {
			id: str(e.id, `${p}.id`),
			title: str(e.title, `${p}.title`),
			category: str(e.category, `${p}.category`),
			description: str(e.description, `${p}.description`),
			summary: str(e.summary, `${p}.summary`),
			premium: bool(e.premium, `${p}.premium`),
			trending: bool(e.trending, `${p}.trending`),
			utility: bool(e.utility, `${p}.utility`),
			premium_notes: strings(e.premium_notes, `${p}.premium_notes`),
			plan: nullableStr(e.plan, `${p}.plan`),
			request_cost: cost,
			doc_url: str(e.doc_url, `${p}.doc_url`),
			params: arr(e.params, `${p}.params`).map((x, j) => catalogParam(x, `${p}.params[${j}]`)),
			examples: arr(e.examples, `${p}.examples`).map((x, j) => {
				const ex = obj(x, `${p}.examples[${j}]`);
				return {
					caption: str(ex.caption, `${p}.examples[${j}].caption`),
					params: paramValues(ex.params, `${p}.examples[${j}].params`)
				};
			})
		};
	});
	if (new Set(endpoints.map((e) => e.id)).size !== endpoints.length)
		fail('endpoints', 'unique ids');
	const categories = arr(o.categories, 'categories').map((raw, i): CatalogCategory => {
		const c = obj(raw, `categories[${i}]`);
		return {
			id: str(c.id, `categories[${i}].id`),
			title: str(c.title, `categories[${i}].title`),
			summary: str(c.summary, `categories[${i}].summary`),
			count: num(c.count, `categories[${i}].count`),
			premium_count: num(c.premium_count, `categories[${i}].premium_count`)
		};
	});
	const known = new Set(categories.map((c) => c.id));
	for (const e of endpoints)
		if (!known.has(e.category)) fail('endpoints', `a known category (got ${e.category})`);
	return { provider: parseProvider(o.provider), categories, endpoints };
}

function nums(value: unknown, path: string, length?: number): (number | null)[] {
	const values = arr(value, path);
	if (length !== undefined && values.length !== length) fail(path, `an array of ${length} values`);
	return values.map((v, i) => nullableNum(v, `${path}[${i}]`));
}

const ROLES: readonly SeriesRole[] = ['open', 'high', 'low', 'close', 'volume', 'value'];
const FORMATS: readonly FactFormat[] = [
	'text',
	'number',
	'integer',
	'percent',
	'currency',
	'date',
	'url',
	'sentiment'
];
const COLUMN_TYPES: readonly ColumnType[] = [
	'text',
	'number',
	'percent',
	'date',
	'datetime',
	'url'
];

function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
	const text = str(value, path);
	if (!allowed.includes(text as T)) fail(path, `one of ${allowed.join(', ')}`);
	return text as T;
}

function viewBase(o: Record<string, unknown>, path: string): ViewBase {
	return {
		id: str(o.id, `${path}.id`),
		title: str(o.title, `${path}.title`),
		subtitle: nullableStr(o.subtitle, `${path}.subtitle`)
	};
}

function parseView(value: unknown, path: string): ProviderView {
	const o = obj(value, path);
	const base = viewBase(o, path);
	const kind = str(o.kind, `${path}.kind`);
	switch (kind) {
		case 'series': {
			const time = arr(o.time, `${path}.time`).map((t, i) => num(t, `${path}.time[${i}]`));
			for (let i = 1; i < time.length; i++)
				if (time[i] <= time[i - 1]) fail(`${path}.time[${i}]`, 'strictly increasing');
			const series = arr(o.series, `${path}.series`).map((s, i) => {
				const c = obj(s, `${path}.series[${i}]`);
				return {
					key: str(c.key, `${path}.series[${i}].key`),
					label: str(c.label, `${path}.series[${i}].label`),
					values: nums(c.values, `${path}.series[${i}].values`, time.length),
					role: oneOf(c.role, ROLES, `${path}.series[${i}].role`),
					unit: nullableStr(c.unit, `${path}.series[${i}].unit`)
				};
			});
			if (series.length === 0) fail(`${path}.series`, 'at least one series');
			const total = num(o.total_points, `${path}.total_points`);
			const truncated = bool(o.truncated, `${path}.truncated`);
			if (truncated !== total > time.length)
				fail(`${path}.truncated`, 'consistent with total_points');
			return {
				...base,
				kind,
				time,
				intraday: bool(o.intraday, `${path}.intraday`),
				series,
				time_note: nullableStr(o.time_note, `${path}.time_note`),
				truncated,
				total_points: total
			};
		}
		case 'table': {
			const columns = arr(o.columns, `${path}.columns`).map((c, i) => {
				const col = obj(c, `${path}.columns[${i}]`);
				return {
					key: str(col.key, `${path}.columns[${i}].key`),
					label: str(col.label, `${path}.columns[${i}].label`),
					type: oneOf(col.type, COLUMN_TYPES, `${path}.columns[${i}].type`)
				};
			});
			const rows = arr(o.rows, `${path}.rows`).map((r, i) => {
				const row = arr(r, `${path}.rows[${i}]`);
				if (row.length !== columns.length) fail(`${path}.rows[${i}]`, `${columns.length} cells`);
				return row.map((cell, j) => {
					if (cell === null || typeof cell === 'string') return cell;
					return num(cell, `${path}.rows[${i}][${j}]`);
				});
			});
			const total = num(o.total_rows, `${path}.total_rows`);
			const truncated = bool(o.truncated, `${path}.truncated`);
			if (truncated !== total > rows.length)
				fail(`${path}.truncated`, 'consistent with total_rows');
			return { ...base, kind, columns, rows, total_rows: total, truncated };
		}
		case 'facts':
			return {
				...base,
				kind,
				groups: arr(o.groups, `${path}.groups`).map((g, i) => {
					const group = obj(g, `${path}.groups[${i}]`);
					return {
						title: nullableStr(group.title, `${path}.groups[${i}].title`),
						items: arr(group.items, `${path}.groups[${i}].items`).map((raw, j): Fact => {
							const f = obj(raw, `${path}.groups[${i}].items[${j}]`);
							const where = `${path}.groups[${i}].items[${j}]`;
							const value =
								f.value === null || typeof f.value === 'string'
									? (f.value as string | null)
									: num(f.value, `${where}.value`);
							const tone =
								f.tone === null || f.tone === undefined
									? null
									: oneOf(f.tone, ['positive', 'negative'] as const, `${where}.tone`);
							return {
								key: str(f.key, `${where}.key`),
								label: str(f.label, `${where}.label`),
								value,
								format: oneOf(f.format, FORMATS, `${where}.format`),
								tone,
								hint: nullableStr(f.hint, `${where}.hint`)
							};
						})
					};
				})
			};
		case 'bars': {
			const labels = strings(o.labels, `${path}.labels`);
			return {
				...base,
				kind,
				labels,
				values: nums(o.values, `${path}.values`, labels.length),
				format: oneOf(o.format, ['number', 'percent', 'currency'] as const, `${path}.format`),
				sign_colors: bool(o.sign_colors, `${path}.sign_colors`),
				value_label: str(o.value_label, `${path}.value_label`)
			};
		}
		case 'feed': {
			const items = arr(o.items, `${path}.items`).map((raw, i): FeedItem => {
				const it = obj(raw, `${path}.items[${i}]`);
				const where = `${path}.items[${i}]`;
				const sentiment =
					it.sentiment === null || it.sentiment === undefined
						? null
						: (() => {
								const s = obj(it.sentiment, `${where}.sentiment`);
								return {
									score: nullableNum(s.score, `${where}.sentiment.score`),
									label: nullableStr(s.label, `${where}.sentiment.label`)
								};
							})();
				return {
					title: str(it.title, `${where}.title`),
					url: nullableStr(it.url, `${where}.url`),
					source: nullableStr(it.source, `${where}.source`),
					published: nullableNum(it.published, `${where}.published`),
					summary: nullableStr(it.summary, `${where}.summary`),
					sentiment,
					tags: strings(it.tags, `${where}.tags`),
					tickers: arr(it.tickers, `${where}.tickers`).map((t, j) => {
						const tk = obj(t, `${where}.tickers[${j}]`);
						return {
							symbol: str(tk.symbol, `${where}.tickers[${j}].symbol`),
							relevance: nullableNum(tk.relevance, `${where}.tickers[${j}].relevance`),
							score: nullableNum(tk.score, `${where}.tickers[${j}].score`),
							label: nullableStr(tk.label, `${where}.tickers[${j}].label`)
						};
					})
				};
			});
			const total = num(o.total_items, `${path}.total_items`);
			const truncated = bool(o.truncated, `${path}.truncated`);
			if (truncated !== total > items.length)
				fail(`${path}.truncated`, 'consistent with total_items');
			return { ...base, kind, items, total_items: total, truncated };
		}
		case 'heatmap': {
			const rows = strings(o.rows, `${path}.rows`);
			const cols = strings(o.cols, `${path}.cols`);
			const values = arr(o.values, `${path}.values`);
			if (values.length !== rows.length) fail(`${path}.values`, `${rows.length} rows`);
			const domain =
				o.domain === null || o.domain === undefined
					? null
					: (nums(o.domain, `${path}.domain`, 2) as [number, number]);
			return {
				...base,
				kind,
				rows,
				cols,
				values: values.map((r, i) => nums(r, `${path}.values[${i}]`, cols.length)),
				scale: oneOf(o.scale, ['diverging', 'sequential'] as const, `${path}.scale`),
				domain
			};
		}
		case 'text': {
			const blocks = arr(o.blocks, `${path}.blocks`).map((raw, i) => {
				const b = obj(raw, `${path}.blocks[${i}]`);
				return {
					heading: nullableStr(b.heading, `${path}.blocks[${i}].heading`),
					subheading: nullableStr(b.subheading, `${path}.blocks[${i}].subheading`),
					body: str(b.body, `${path}.blocks[${i}].body`),
					badge: nullableStr(b.badge, `${path}.blocks[${i}].badge`)
				};
			});
			const total = num(o.total_blocks, `${path}.total_blocks`);
			const truncated = bool(o.truncated, `${path}.truncated`);
			if (truncated !== total > blocks.length)
				fail(`${path}.truncated`, 'consistent with total_blocks');
			return { ...base, kind, blocks, total_blocks: total, truncated };
		}
		default:
			fail(`${path}.kind`, 'a known view kind (series, table, facts, bars, feed, heatmap, text)');
	}
}

export function parseQueryResponse(json: unknown): QueryResponse {
	const o = obj(json, 'response');
	const status = oneOf(o.status, STATUSES, 'status');
	const message = nullableStr(o.message, 'message');
	const views = arr(o.views, 'views').map((v, i) => parseView(v, `views[${i}]`));
	if (status !== 'ok' && views.length > 0) fail('views', 'empty unless the status is ok');
	if (status !== 'ok' && !message) fail('message', 'present when the status is not ok');
	const omitted =
		o.raw_omitted === null || o.raw_omitted === undefined
			? null
			: (() => {
					const r = obj(o.raw_omitted, 'raw_omitted');
					return {
						bytes: num(r.bytes, 'raw_omitted.bytes'),
						reason: str(r.reason, 'raw_omitted.reason')
					};
				})();
	return {
		provider: str(o.provider, 'provider'),
		endpoint: str(o.endpoint, 'endpoint'),
		title: str(o.title, 'title'),
		status,
		message,
		cached: bool(o.cached, 'cached'),
		fetched_at: nullableNum(o.fetched_at, 'fetched_at'),
		elapsed_ms: num(o.elapsed_ms, 'elapsed_ms'),
		bytes: num(o.bytes, 'bytes'),
		params: paramValues(o.params, 'params'),
		views,
		raw: o.raw ?? null,
		raw_omitted: omitted,
		notes: strings(o.notes, 'notes')
	};
}
