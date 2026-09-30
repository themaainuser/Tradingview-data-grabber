/**
 * Ready-made filter conditions generated from the indicator registry.
 *
 * Nothing here is data: each preset is a condition template (for example "RSI(14) crosses above
 * 70") derived from an indicator's declared reference levels and pane type. Because they are
 * generated, every indicator output the registry gains automatically gets its presets.
 */
import { newCondition } from '$lib/filters/tree';
import type { Condition } from '$lib/filters/types';
import { defaultSeriesCatalog, getIndicator } from '$lib/indicators';
import { fieldLabel } from './fields';

export interface FilterPreset {
	id: string;
	label: string;
	group: string;
	haystack: string;
	/** Uses the whole sample, so it is descriptive rather than tradeable. */
	lookahead: boolean;
	build(): Condition[];
}

type Init = Partial<Omit<Condition, 'type' | 'id'>>;

function preset(
	id: string,
	label: string,
	group: string,
	init: Init,
	lookahead = false,
	keywords = ''
): FilterPreset {
	return {
		id,
		label,
		group,
		haystack: `${label} ${group} ${keywords}`.toLowerCase(),
		lookahead,
		build: () => [newCondition(init)]
	};
}

let cached: FilterPreset[] | null = null;

export function generatePresets(): FilterPreset[] {
	if (cached) return cached;
	const presets: FilterPreset[] = [];

	for (const bar of ['close', 'high', 'low', 'volume'] as const) {
		const label = fieldLabel(bar);
		const group = 'Price & volume';
		for (const bars of [20, 55, 100]) {
			presets.push(
				preset(`${bar}:new_high:${bars}`, `${label} makes a ${bars}-bar high`, group, {
					field: bar,
					op: 'new_high',
					value: bars
				})
			);
			presets.push(
				preset(`${bar}:new_low:${bars}`, `${label} makes a ${bars}-bar low`, group, {
					field: bar,
					op: 'new_low',
					value: bars
				})
			);
		}
		presets.push(
			preset(`${bar}:rising:3`, `${label} rose 3 bars in a row`, group, {
				field: bar,
				op: 'rising',
				value: 3
			})
		);
		presets.push(
			preset(`${bar}:falling:3`, `${label} fell 3 bars in a row`, group, {
				field: bar,
				op: 'falling',
				value: 3
			})
		);
	}
	presets.push(
		preset(
			'volume:top10',
			'Volume in the top 10% (full sample)',
			'Price & volume',
			{ field: 'volume', op: 'top_pct', value: 10 },
			true
		)
	);

	for (const entry of defaultSeriesCatalog()) {
		const definition = getIndicator(entry.id)!;
		const label = fieldLabel(entry.key);
		const group = entry.category;
		const key = entry.key;
		const id = (suffix: string) => `${key}:${suffix}`;
		const words = `${entry.name} ${entry.outputLabel}`;
		const guides = definition.guides ? [...definition.guides].sort((a, b) => a - b) : [];

		if (entry.pane === 'price') {
			presets.push(
				preset(
					id('close>'),
					`Close above ${label}`,
					group,
					{ field: 'close', op: 'gt', rhs: key },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('close<'),
					`Close below ${label}`,
					group,
					{ field: 'close', op: 'lt', rhs: key },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('close^'),
					`Close crosses above ${label}`,
					group,
					{ field: 'close', op: 'crosses_above', rhs: key },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('closev'),
					`Close crosses below ${label}`,
					group,
					{ field: 'close', op: 'crosses_below', rhs: key },
					false,
					words
				)
			);
			continue;
		}
		if (guides.length) {
			const low = guides[0];
			const high = guides[guides.length - 1];
			presets.push(
				preset(
					id('gt-high'),
					`${label} above ${high}`,
					group,
					{ field: key, op: 'gt', value: high },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('lt-low'),
					`${label} below ${low}`,
					group,
					{ field: key, op: 'lt', value: low },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('x-high'),
					`${label} crosses above ${high}`,
					group,
					{ field: key, op: 'crosses_above', value: high },
					false,
					words
				)
			);
			presets.push(
				preset(
					id('x-low'),
					`${label} crosses below ${low}`,
					group,
					{ field: key, op: 'crosses_below', value: low },
					false,
					words
				)
			);
			if (guides.length > 1 && low !== high) {
				presets.push(
					preset(
						id('between'),
						`${label} between ${low} and ${high}`,
						group,
						{ field: key, op: 'between', value: low, value2: high },
						false,
						words
					)
				);
			}
		}
		presets.push(
			preset(
				id('rising'),
				`${label} rose 3 bars in a row`,
				group,
				{ field: key, op: 'rising', value: 3 },
				false,
				words
			)
		);
		presets.push(
			preset(
				id('falling'),
				`${label} fell 3 bars in a row`,
				group,
				{ field: key, op: 'falling', value: 3 },
				false,
				words
			)
		);
		presets.push(
			preset(
				id('hi20'),
				`${label} makes a 20-bar high`,
				group,
				{ field: key, op: 'new_high', value: 20 },
				false,
				words
			)
		);
		presets.push(
			preset(
				id('lo20'),
				`${label} makes a 20-bar low`,
				group,
				{ field: key, op: 'new_low', value: 20 },
				false,
				words
			)
		);
		presets.push(
			preset(
				id('top10'),
				`${label} in the top 10% (full sample)`,
				group,
				{ field: key, op: 'top_pct', value: 10 },
				true,
				words
			)
		);
		presets.push(
			preset(
				id('bottom10'),
				`${label} in the bottom 10% (full sample)`,
				group,
				{ field: key, op: 'bottom_pct', value: 10 },
				true,
				words
			)
		);
	}
	cached = presets;
	return presets;
}
