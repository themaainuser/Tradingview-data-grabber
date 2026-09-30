import type { Operator, OperatorSpec } from './types';

const spec = (
	s: Omit<OperatorSpec, 'ordered' | 'lookahead' | 'allowsField'> &
		Partial<Pick<OperatorSpec, 'ordered' | 'lookahead' | 'allowsField'>>
): OperatorSpec => ({
	ordered: false,
	lookahead: false,
	allowsField: false,
	...s
});

export const OPERATORS: readonly OperatorSpec[] = [
	spec({
		id: 'gt',
		label: 'is above',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field is strictly greater than the value or other field.'
	}),
	spec({
		id: 'gte',
		label: 'is at or above',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field is greater than or equal to the value or other field.'
	}),
	spec({
		id: 'lt',
		label: 'is below',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field is strictly less than the value or other field.'
	}),
	spec({
		id: 'lte',
		label: 'is at or below',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field is less than or equal to the value or other field.'
	}),
	spec({
		id: 'eq',
		label: 'equals',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field equals the value or other field (within floating-point tolerance).'
	}),
	spec({
		id: 'neq',
		label: 'does not equal',
		family: 'compare',
		operand: 'value',
		allowsField: true,
		description: 'Field differs from the value or other field; missing values never match.'
	}),
	spec({
		id: 'between',
		label: 'is between',
		family: 'compare',
		operand: 'range',
		description: 'Field lies within the inclusive range.'
	}),
	spec({
		id: 'outside',
		label: 'is outside',
		family: 'compare',
		operand: 'range',
		description: 'Field lies strictly outside the inclusive range.'
	}),
	spec({
		id: 'crosses_above',
		label: 'crosses above',
		family: 'series',
		operand: 'value',
		allowsField: true,
		ordered: true,
		description: 'Was at or below on the previous bar and is above now.'
	}),
	spec({
		id: 'crosses_below',
		label: 'crosses below',
		family: 'series',
		operand: 'value',
		allowsField: true,
		ordered: true,
		description: 'Was at or above on the previous bar and is below now.'
	}),
	spec({
		id: 'rising',
		label: 'rose for N bars',
		family: 'series',
		operand: 'count',
		ordered: true,
		description: 'Increased on each of the last N bars.'
	}),
	spec({
		id: 'falling',
		label: 'fell for N bars',
		family: 'series',
		operand: 'count',
		ordered: true,
		description: 'Decreased on each of the last N bars.'
	}),
	spec({
		id: 'new_high',
		label: 'makes a new N-bar high',
		family: 'series',
		operand: 'count',
		ordered: true,
		description: 'Exceeds every one of the previous N values.'
	}),
	spec({
		id: 'new_low',
		label: 'makes a new N-bar low',
		family: 'series',
		operand: 'count',
		ordered: true,
		description: 'Is below every one of the previous N values.'
	}),
	spec({
		id: 'top_pct',
		label: 'is in the top X%',
		family: 'distribution',
		operand: 'percent',
		lookahead: true,
		description:
			'At or above the (100-X)th percentile of the whole sample. Uses future data: descriptive only.'
	}),
	spec({
		id: 'bottom_pct',
		label: 'is in the bottom X%',
		family: 'distribution',
		operand: 'percent',
		lookahead: true,
		description:
			'At or below the Xth percentile of the whole sample. Uses future data: descriptive only.'
	}),
	spec({
		id: 'is_valid',
		label: 'has a value',
		family: 'validity',
		operand: 'none',
		description: 'Field is a finite number (indicator warm-up rows are excluded).'
	}),
	spec({
		id: 'is_missing',
		label: 'has no value',
		family: 'validity',
		operand: 'none',
		description: 'Field is missing, e.g. during indicator warm-up.'
	}),
	spec({
		id: 'in',
		label: 'is one of',
		family: 'text',
		operand: 'text',
		description: 'Text equals any item of the comma separated list (case-insensitive).'
	}),
	spec({
		id: 'not_in',
		label: 'is none of',
		family: 'text',
		operand: 'text',
		description: 'Text equals none of the comma separated items.'
	}),
	spec({
		id: 'contains',
		label: 'contains',
		family: 'text',
		operand: 'text',
		description: 'Text contains the fragment (case-insensitive).'
	}),
	spec({
		id: 'starts_with',
		label: 'starts with',
		family: 'text',
		operand: 'text',
		description: 'Text starts with the fragment (case-insensitive).'
	})
];

const BY_ID = new Map<Operator, OperatorSpec>(OPERATORS.map((o) => [o.id, o]));

export function getOperator(id: Operator): OperatorSpec {
	const found = BY_ID.get(id);
	if (!found) throw new Error(`Unknown operator: ${id}`);
	return found;
}

export function isOperator(value: unknown): value is Operator {
	return typeof value === 'string' && BY_ID.has(value as Operator);
}

/** Operators that apply to a column of the given kind on a source with the given ordering. */
export function operatorsFor(kind: 'numeric' | 'text', ordered: boolean): OperatorSpec[] {
	return OPERATORS.filter((o) =>
		kind === 'text' ? o.family === 'text' : o.family !== 'text' && (ordered || !o.ordered)
	);
}
