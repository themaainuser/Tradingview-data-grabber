/** Geometry for the semicircular gauge: 0 sits at the left end, 100 at the right end. */

export const GAUGE = {
	width: 360,
	height: 214,
	cx: 180,
	cy: 184,
	radius: 146,
	stroke: 20
} as const;

/** Degrees of arc per score point across the half circle. */
const DEGREES_PER_POINT = 1.8;

const clampScore = (score: number) => Math.min(100, Math.max(0, score));

/** Angle in degrees measured counter-clockwise from the +x axis: score 0 is 180, score 100 is 0. */
export function scoreAngle(score: number): number {
	return 180 - clampScore(score) * DEGREES_PER_POINT;
}

/** Point on a circle of the given radius, at `degrees` counter-clockwise from +x (SVG y points down). */
export function polar(
	cx: number,
	cy: number,
	radius: number,
	degrees: number
): { x: number; y: number } {
	const radians = (degrees * Math.PI) / 180;
	return { x: cx + radius * Math.cos(radians), y: cy - radius * Math.sin(radians) };
}

const round = (n: number) => Math.round(n * 100) / 100;

/** SVG path for the arc between two scores, inset by `gapDegrees` at each end so segments do not touch. */
export function arcPath(from: number, to: number, gapDegrees = 1.2): string {
	const { cx, cy, radius } = GAUGE;
	const start = polar(cx, cy, radius, scoreAngle(from) - gapDegrees);
	const end = polar(cx, cy, radius, scoreAngle(to) + gapDegrees);
	// Every segment is at most a quarter turn, so the small-arc flag is always 0; the sweep flag 1
	// draws clockwise on screen, which is left-to-right across the top.
	return `M ${round(start.x)} ${round(start.y)} A ${radius} ${radius} 0 0 1 ${round(end.x)} ${round(end.y)}`;
}

/** Needle rotation in degrees for CSS `rotate()`, with the needle drawn pointing straight up at 50. */
export function needleRotation(score: number): number {
	return clampScore(score) * DEGREES_PER_POINT - 90;
}
