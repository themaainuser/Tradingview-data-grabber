import type { FilterCatalog } from '$lib/filters/catalog';
import { newCondition } from '$lib/filters/tree';
import type { FilterPreset } from '$lib/explorer/presets';
import type { ResearchTable } from './columns';

function preset(
	id: string,
	label: string,
	...init: Parameters<typeof newCondition>[0][]
): FilterPreset {
	return {
		id,
		label,
		group: 'Research screens',
		haystack: label.toLowerCase(),
		lookahead: false,
		build: () => init.map((i) => newCondition(i))
	};
}

/** Screens that make sense for any research report; they only reference columns that always exist. */
const PRESETS: FilterPreset[] = [
	preset('fwd-sharpe-pos', 'Forward Sharpe above 0', {
		field: 'forward.sharpe',
		op: 'gt',
		value: 0
	}),
	preset('fwd-sharpe-1', 'Forward Sharpe above 1', { field: 'forward.sharpe', op: 'gt', value: 1 }),
	preset('fwd-beats-bh', 'Beat buy-and-hold over the full sample', {
		field: 'rel.excess_return',
		op: 'gt',
		value: 0
	}),
	preset('fold-all-pos', 'Every forward fold positive', {
		field: 'fold.return_min',
		op: 'gt',
		value: 0
	}),
	preset('fold-most-pos', 'At least 3 positive forward folds', {
		field: 'fold.positive',
		op: 'gte',
		value: 3
	}),
	preset('no-collapse', 'Forward Sharpe within 50% of in-sample', {
		field: 'rel.forward_retention',
		op: 'gte',
		value: 0.5
	}),
	preset('shallow-dd', 'Forward drawdown shallower than -20%', {
		field: 'forward.max_drawdown_pct',
		op: 'gt',
		value: -20
	}),
	preset('enough-trades', 'At least 10 forward trades', {
		field: 'forward.trades',
		op: 'gte',
		value: 10
	}),
	preset('sma-only', 'SMA crossover family', { field: 'family', op: 'contains', text: 'SMA' }),
	preset('rsi-only', 'RSI mean-reversion family', { field: 'family', op: 'contains', text: 'RSI' }),
	preset('fwd-missing', 'Forward metrics unavailable (short capture)', {
		field: 'forward.sharpe',
		op: 'is_missing'
	})
];

export function createResearchCatalog(table: ResearchTable): FilterCatalog {
	const options = table.columns.map((c) => ({
		key: c.key,
		label: `${c.group}: ${c.label}`,
		group: c.group,
		description: c.description,
		haystack: `${c.group} ${c.label} ${c.key}`.toLowerCase()
	}));
	const known = new Set(table.columns.map((c) => c.key));
	return {
		ordered: false,
		options,
		kindOf: (key) => table.column(key)?.kind ?? null,
		label: (key) => {
			const column = table.column(key);
			return column ? `${column.group}: ${column.label}` : key;
		},
		presets: PRESETS.filter((p) => p.build().every((c) => known.has(c.field)))
	};
}
