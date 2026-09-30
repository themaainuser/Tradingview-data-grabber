/** Data handed to the canvas chart. Values are typed arrays aligned to the bar index. */

export interface ChartSeries {
	key: string;
	label: string;
	/** A CSS custom property name such as `--chart-1`, or any CSS colour. */
	color: string;
	values: Float64Array;
	style: 'line' | 'histogram';
}

export interface ChartPane {
	id: string;
	label: string;
	series: ChartSeries[];
	guides: readonly number[];
}

export const CHART_PALETTE = [
	'--chart-1',
	'--chart-2',
	'--chart-3',
	'--chart-4',
	'--chart-5'
] as const;
