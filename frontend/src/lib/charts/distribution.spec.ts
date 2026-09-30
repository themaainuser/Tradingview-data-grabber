import { describe, expect, it } from 'vitest';
import {
	binCenters,
	binIndexOf,
	decimalsFor,
	formatSignedPct,
	histogramLabels
} from './distribution';

const edges = [-1, -0.5, 0, 0.5, 1];

describe('binCenters', () => {
	it('returns the midpoint of every bin', () => {
		expect(binCenters(edges)).toEqual([-0.75, -0.25, 0.25, 0.75]);
	});
	it('is empty without at least two edges', () => {
		expect(binCenters([])).toEqual([]);
		expect(binCenters([1])).toEqual([]);
	});
});

describe('binIndexOf', () => {
	it('finds the bin and treats inner edges as belonging to the upper bin', () => {
		expect(binIndexOf(edges, -0.75)).toBe(0);
		expect(binIndexOf(edges, 0)).toBe(2);
		expect(binIndexOf(edges, -0.5)).toBe(1);
	});
	it('includes both outer edges', () => {
		expect(binIndexOf(edges, -1)).toBe(0);
		expect(binIndexOf(edges, 1)).toBe(3);
	});
	it('returns -1 outside the bins, for NaN, and for degenerate edges', () => {
		expect(binIndexOf(edges, -1.01)).toBe(-1);
		expect(binIndexOf(edges, 1.01)).toBe(-1);
		expect(binIndexOf(edges, NaN)).toBe(-1);
		expect(binIndexOf([], 0)).toBe(-1);
		expect(binIndexOf([0], 0)).toBe(-1);
	});
});

describe('formatSignedPct', () => {
	it('signs with a real minus and never prints negative zero', () => {
		expect(formatSignedPct(0.254)).toBe('+0.25%');
		expect(formatSignedPct(-0.254)).toBe('\u22120.25%');
		expect(formatSignedPct(-0.001)).toBe('0.00%');
		expect(formatSignedPct(0)).toBe('0.00%');
	});
	it('honours the decimals and shows a dash for non-finite values', () => {
		expect(formatSignedPct(1.23456, 3)).toBe('+1.235%');
		expect(formatSignedPct(NaN)).toBe('\u2014');
		expect(formatSignedPct(Infinity)).toBe('\u2014');
	});
});

describe('histogramLabels', () => {
	it('labels bin centres with enough decimals to be distinct', () => {
		expect(histogramLabels(edges)).toEqual(['\u22120.8%', '\u22120.3%', '+0.3%', '+0.8%']);
		const fine = [0, 0.004, 0.008, 0.012];
		const labels = histogramLabels(fine);
		expect(new Set(labels).size).toBe(labels.length);
		expect(labels[0]).toBe('+0.002%');
	});
	it('decimalsFor falls back for a non-positive step', () => {
		expect(decimalsFor(0)).toBe(2);
		expect(decimalsFor(-1)).toBe(2);
	});
});
