import { describe, expect, it } from 'vitest';
import type { FearGreedBand } from '$lib/api/contracts';
import { bandOf, formatDelta, rangeStart, rangeSummary, zoneCounts } from './stats';

const DAY = 86_400;
const bands: FearGreedBand[] = [
	{ key: 'extreme_fear', label: 'Extreme fear', from: 0, to: 20 },
	{ key: 'fear', label: 'Fear', from: 20, to: 40 },
	{ key: 'neutral', label: 'Neutral', from: 40, to: 60 },
	{ key: 'greed', label: 'Greed', from: 60, to: 80 },
	{ key: 'extreme_greed', label: 'Extreme greed', from: 80, to: 100 }
];
const days = (n: number) => Array.from({ length: n }, (_, i) => 1_700_000_000 + i * DAY);

describe('bandOf', () => {
	it.each([
		[0, 'extreme_fear'],
		[19, 'extreme_fear'],
		[20, 'fear'],
		[59, 'neutral'],
		[60, 'greed'],
		[79, 'greed'],
		[80, 'extreme_greed'],
		[100, 'extreme_greed']
	])('puts %i in %s', (score, key) => expect(bandOf(score, bands)?.key).toBe(key));

	it('returns null outside the scale instead of guessing', () => {
		expect(bandOf(-1, bands)).toBeNull();
		expect(bandOf(101, bands)).toBeNull();
		expect(bandOf(50, [])).toBeNull();
	});
});

describe('rangeStart', () => {
	const time = days(100);
	it('starts at the first reading inside the trailing window', () => {
		expect(rangeStart(time, 30)).toBe(69); // the reading exactly 30 days before the last is included
		expect(rangeStart(time, 90)).toBe(9);
	});
	it('returns 0 for "all", for a window longer than the data, and for no data', () => {
		expect(rangeStart(time, null)).toBe(0);
		expect(rangeStart(time, 365)).toBe(0);
		expect(rangeStart([], 30)).toBe(0);
	});
	it('handles a single reading', () => expect(rangeStart([5], 30)).toBe(0));
});

describe('zoneCounts', () => {
	it('counts readings per band and shares sum to one', () => {
		const zones = zoneCounts([5, 25, 25, 45, 65, 65, 65, 90], 0, bands);
		expect(zones.map((z) => z.count)).toEqual([1, 2, 1, 3, 1]);
		expect(zones.reduce((sum, z) => sum + z.share, 0)).toBeCloseTo(1);
		expect(zones[3].share).toBeCloseTo(3 / 8);
	});
	it('only counts readings from the start index', () => {
		expect(zoneCounts([5, 5, 90], 2, bands).map((z) => z.count)).toEqual([0, 0, 0, 0, 1]);
	});
	it('reports zero shares, not NaN, for an empty range', () => {
		const zones = zoneCounts([], 0, bands);
		expect(zones.every((z) => z.count === 0 && z.share === 0)).toBe(true);
	});
});

describe('rangeSummary', () => {
	const time = days(5);
	it('reports mean, extremes (latest tie wins) and net change', () => {
		const s = rangeSummary(time, [30, 80, 50, 80, 40], 0)!;
		expect(s.count).toBe(5);
		expect(s.mean).toBeCloseTo(56);
		expect(s.high).toEqual({ score: 80, time: time[3] });
		expect(s.low).toEqual({ score: 30, time: time[0] });
		expect(s.change).toBe(10);
	});
	it('respects the start index', () => {
		const s = rangeSummary(time, [10, 80, 50, 60, 70], 2)!;
		expect(s.count).toBe(3);
		expect(s.low.score).toBe(50);
		expect(s.change).toBe(20);
	});
	it('is null for an empty range', () => expect(rangeSummary([], [], 0)).toBeNull());
});

describe('formatDelta', () => {
	it('signs with a real minus', () => {
		expect(formatDelta(3)).toBe('+3');
		expect(formatDelta(-5)).toBe('\u22125');
		expect(formatDelta(0)).toBe('0');
	});
});
