/** Shared prop types of the chart components. Colours are CSS colours, usually `var(--token)`. */

export interface AreaSeries {
	key: string;
	label: string;
	color: string;
	/** One value per `time` entry; null (or NaN) breaks the line. */
	values: readonly (number | null)[];
	kind?: 'line' | 'area';
	axis?: 'left' | 'right';
	dashed?: boolean;
}

/** Horizontal band on the left axis, drawn behind the series. */
export interface AreaBand {
	from: number;
	to: number;
	color: string;
	label?: string;
}

export interface BarMarker {
	index: number;
	label: string;
}

export interface HBarMarker {
	value: number;
	label: string;
}

export interface HBarRange {
	low: number;
	high: number;
	label?: string;
}

export interface HeatmapLegend {
	low: string;
	high: string;
}

export interface TooltipRow {
	label: string;
	value: string;
	color?: string;
	swatch?: 'dot' | 'line';
}
