import { describe, expect, it } from 'vitest';
import { BAND_FILL, BAND_MEANING, BAND_TEXT, meterGradient } from './bands';
import { arcPath, GAUGE, needleRotation, polar, scoreAngle } from './gauge';

describe('scoreAngle', () => {
	it('runs from the left end (0) over the top (50) to the right end (100)', () => {
		expect(scoreAngle(0)).toBe(180);
		expect(scoreAngle(50)).toBe(90);
		expect(scoreAngle(100)).toBe(0);
	});
	it('clamps scores outside the scale', () => {
		expect(scoreAngle(-20)).toBe(180);
		expect(scoreAngle(140)).toBe(0);
	});
});

describe('polar', () => {
	it('places angles on the circle with SVG y pointing down', () => {
		const right = polar(100, 100, 50, 0);
		expect(right.x).toBeCloseTo(150);
		expect(right.y).toBeCloseTo(100);
		const top = polar(100, 100, 50, 90);
		expect(top.x).toBeCloseTo(100);
		expect(top.y).toBeCloseTo(50); // above the centre means a smaller y
	});
});

describe('needleRotation', () => {
	it('points left at 0, straight up at 50 and right at 100', () => {
		expect(needleRotation(0)).toBe(-90);
		expect(needleRotation(50)).toBe(0);
		expect(needleRotation(100)).toBe(90);
		expect(needleRotation(67)).toBeCloseTo(30.6);
	});
});

describe('arcPath', () => {
	it('starts on the left of its span and ends on the right, both on the gauge circle', () => {
		const path = arcPath(20, 40, 0);
		// Tokens: M sx sy A rx ry rotation large-arc sweep ex ey
		const [, sx, sy, , , , , , , ex, ey] = path.split(' ');
		const start = polar(GAUGE.cx, GAUGE.cy, GAUGE.radius, scoreAngle(20));
		const end = polar(GAUGE.cx, GAUGE.cy, GAUGE.radius, scoreAngle(40));
		expect(Number(sx)).toBeCloseTo(start.x, 1);
		expect(Number(sy)).toBeCloseTo(start.y, 1);
		expect(Number(ex)).toBeCloseTo(end.x, 1);
		expect(Number(ey)).toBeCloseTo(end.y, 1);
		expect(Number(sx)).toBeLessThan(Number(ex));
	});
	it('insets by the gap so neighbouring segments do not touch', () => {
		const gapped = arcPath(20, 40, 2).split(' ');
		const flush = arcPath(20, 40, 0).split(' ');
		expect(Number(gapped[1])).toBeGreaterThan(Number(flush[1]));
	});
	it('never contains NaN', () => {
		for (const [a, b] of [
			[0, 20],
			[20, 40],
			[40, 60],
			[60, 80],
			[80, 100]
		]) {
			expect(arcPath(a, b)).not.toContain('NaN');
		}
	});
});

describe('band styling', () => {
	const keys = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'] as const;
	it('defines a fill, a text colour and a meaning for every band, using only design tokens', () => {
		for (const key of keys) {
			expect(BAND_FILL[key]).toMatch(/^(var\(--[a-z0-9-]+\)|color-mix\(.*var\(--.*\))$/);
			expect(BAND_TEXT[key]).toMatch(/^var\(--[a-z0-9-]+\)$/);
			expect(BAND_MEANING[key].length).toBeGreaterThan(10);
			expect(BAND_FILL[key] + BAND_TEXT[key]).not.toMatch(/#[0-9a-f]{3,6}/i);
		}
	});
});

describe('meterGradient', () => {
	const bands = [
		{ key: 'extreme_fear', from: 0, to: 20 },
		{ key: 'fear', from: 20, to: 40 },
		{ key: 'neutral', from: 40, to: 60 },
		{ key: 'greed', from: 60, to: 80 },
		{ key: 'extreme_greed', from: 80, to: 100 }
	] as const;
	it('paints every band over exactly its own span with hard stops', () => {
		const css = meterGradient(bands);
		expect(css.startsWith('linear-gradient(to right, ')).toBe(true);
		for (const b of bands) expect(css).toContain(`${BAND_FILL[b.key]} ${b.from}% ${b.to}%`);
	});
});
