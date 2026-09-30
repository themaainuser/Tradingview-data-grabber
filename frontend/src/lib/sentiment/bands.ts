/**
 * Colour and wording for the five Fear & Greed bands, shared by the gauge, pills, chart bands and
 * zone bar so one reading is never drawn in two different colours.
 *
 * DESIGN.md allows no chromatic colour outside its tokens, so fear is the documented coral and
 * orange, greed is the documented success green, and neutral is the muted ink. The `*-ink`
 * variants are the brand colours darkened in the light theme, so arcs and text stay readable.
 */
import type { BandKey } from '$lib/api/contracts';

/** Fill for arcs, dots and chart bands. */
export const BAND_FILL: Record<BandKey, string> = {
	extreme_fear: 'var(--coral-ink)',
	fear: 'var(--orange-ink)',
	neutral: 'var(--ink-muted)',
	greed: 'var(--band-greed)',
	extreme_greed: 'var(--success-ink)'
};

/** Colour for text naming a band; every value here clears 4.5:1 on canvas and the surfaces. */
export const BAND_TEXT: Record<BandKey, string> = {
	extreme_fear: 'var(--coral-ink)',
	fear: 'var(--orange-ink)',
	neutral: 'var(--ink)',
	greed: 'var(--success-ink)',
	extreme_greed: 'var(--success-ink)'
};

/** A short plain-English reading of what a band implies, for the gauge caption. */
export const BAND_MEANING: Record<BandKey, string> = {
	extreme_fear:
		'Investors are very worried; past readings this low have often coincided with oversold markets.',
	fear: 'Sentiment is cautious and leaning negative.',
	neutral: 'Sentiment is balanced between fear and greed.',
	greed: 'Sentiment is optimistic and leaning positive.',
	extreme_greed:
		'Investors are very optimistic; readings this high can signal an overheated market.'
};

/** Hard-stop gradient that paints each band's span of a 0-100 track, for score meters. */
export function meterGradient(
	bands: readonly { key: BandKey; from: number; to: number }[]
): string {
	const stops = bands.map((b) => `${BAND_FILL[b.key]} ${b.from}% ${b.to}%`).join(', ');
	return `linear-gradient(to right, ${stops})`;
}
