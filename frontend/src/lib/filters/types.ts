/**
 * Filter model shared by the bar explorer and the research table.
 *
 * A filter is a tree: groups combine children with AND / OR (optionally negated) and leaves are
 * conditions on one field. Fields are opaque string keys resolved by a `ColumnSource`, so the
 * same engine filters indicator series (one value per bar) and research metrics (one value per
 * strategy) without knowing either.
 */

export type Operator =
	| 'gt'
	| 'gte'
	| 'lt'
	| 'lte'
	| 'eq'
	| 'neq'
	| 'between'
	| 'outside'
	| 'crosses_above'
	| 'crosses_below'
	| 'rising'
	| 'falling'
	| 'new_high'
	| 'new_low'
	| 'top_pct'
	| 'bottom_pct'
	| 'is_valid'
	| 'is_missing'
	| 'in'
	| 'not_in'
	| 'contains'
	| 'starts_with';

export interface Condition {
	type: 'condition';
	id: string;
	enabled: boolean;
	/** Field key; '' means "not chosen yet" and the condition is skipped. */
	field: string;
	op: Operator;
	/** Threshold, bar count (rising / new_high...) or percent (top_pct...). */
	value: number;
	/** Upper bound for between / outside. */
	value2: number;
	/** Compare against another field instead of `value` (comparison and cross operators). */
	rhs: string | null;
	/** Comma separated list (in / not_in) or fragment (contains / starts_with). */
	text: string;
}

export type GroupMode = 'and' | 'or';

export interface FilterGroup {
	type: 'group';
	id: string;
	enabled: boolean;
	mode: GroupMode;
	negate: boolean;
	children: FilterNode[];
}

export type FilterNode = Condition | FilterGroup;

/** Read-only view of the data a filter runs against. */
export interface ColumnSource {
	readonly length: number;
	/** True when rows are a time series, which unlocks previous-row operators (crosses, rising...). */
	readonly ordered: boolean;
	/** Numeric column (NaN = missing) or null when the field does not exist / is not numeric. */
	numeric(field: string): Float64Array | null;
	/** Text column or null when the field does not exist / is not text. */
	text(field: string): readonly string[] | null;
}

export type IssueLevel = 'invalid';

export interface FilterIssue {
	nodeId: string;
	message: string;
}

export interface EvaluationResult {
	/** 1 where the row passes; null when no active condition exists (everything passes). */
	mask: Uint8Array | null;
	matched: number;
	total: number;
	/** Conditions that could not be evaluated. They match nothing and are reported, never ignored. */
	issues: FilterIssue[];
}

export type OperandKind = 'none' | 'value' | 'range' | 'count' | 'percent' | 'text';
export type OperatorFamily = 'compare' | 'series' | 'distribution' | 'validity' | 'text';

export interface OperatorSpec {
	id: Operator;
	label: string;
	family: OperatorFamily;
	operand: OperandKind;
	/** Whether the right-hand side may be another field. */
	allowsField: boolean;
	/** Needs previous rows, so only valid on ordered sources. */
	ordered: boolean;
	/** Uses the whole sample (peeks at the future); descriptive, not tradeable. */
	lookahead: boolean;
	description: string;
}
