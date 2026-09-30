/**
 * Keeps the implementation honest against frontend/DESIGN.md (the design source of truth):
 * every color, spacing, radius and type token in its front matter must exist in layout.css with
 * the same value, and every text/background pairing the UI uses must meet WCAG contrast.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const read = (relative: string) =>
	readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const design = read('../../../DESIGN.md');
const css = read('../../routes/layout.css');

type Section = Record<string, string | Record<string, string>>;

/** Minimal reader for the front matter: two-space nesting, `key: value`, optional single or double quotes (prettier may rewrite them). */
function frontMatter(source: string): Record<string, Section> {
	const body = source.split(/^---$/m)[1];
	const out: Record<string, Section> = {};
	let top = '';
	let sub = '';
	for (const line of body.split('\n')) {
		const match = /^(\s*)([\w-]+):\s*(.*)$/.exec(line);
		if (!match) continue;
		const [, indent, key, raw] = match;
		const value = raw.replace(/^(["'])(.*)\1$/, '$2');
		if (indent.length === 0) {
			top = key;
			if (value === '') out[top] = {};
		} else if (indent.length === 2 && out[top]) {
			if (value === '') {
				sub = key;
				out[top][key] = {};
			} else out[top][key] = value;
		} else if (indent.length === 4 && typeof out[top]?.[sub] === 'object') {
			(out[top][sub] as Record<string, string>)[key] = value;
		}
	}
	return out;
}

const tokens = frontMatter(design);

const rootBlock = /:root\s*\{([\s\S]*?)\n\}/.exec(css)![1];
const themeBlock = /@theme\s*\{([\s\S]*?)\n\}/.exec(css)![1];
const declared = (block: string, name: string) =>
	new RegExp(`--${name}:\\s*([^;]+);`).exec(block)?.[1].trim().toLowerCase();

describe('DESIGN.md front matter', () => {
	it('parses the sections the implementation depends on', () => {
		expect(Object.keys(tokens)).toEqual(
			expect.arrayContaining(['colors', 'typography', 'rounded', 'spacing', 'components'])
		);
		expect(Object.keys(tokens.colors).length).toBeGreaterThanOrEqual(17);
	});
});

describe('color tokens', () => {
	it.each(Object.entries(tokens.colors) as [string, string][])(
		'%s is declared in :root',
		(name, value) => {
			expect(declared(rootBlock, name)).toBe(value.toLowerCase());
		}
	);
});

describe('spacing tokens', () => {
	it.each(Object.entries(tokens.spacing) as [string, string][])(
		'%s is declared as --space-%s',
		(name, value) => {
			expect(declared(rootBlock, `space-${name}`)).toBe(value.toLowerCase());
		}
	);
});

describe('radius tokens', () => {
	it.each(
		(Object.entries(tokens.rounded) as [string, string][]).filter(([name]) => name !== 'full')
	)('%s is declared as --radius-%s', (name, value) => {
		expect(declared(themeBlock, `radius-${name}`)).toBe(value.toLowerCase());
	});
});

describe('typography tokens', () => {
	const utility = (name: string) =>
		new RegExp(`@utility type-${name}\\s*\\{([\\s\\S]*?)\\n\\}`).exec(css)?.[1] ?? '';
	const first = (block: string, property: string) =>
		new RegExp(`(?:^|\\n|\\t)\\s*${property}:\\s*([^;]+);`).exec(block)?.[1].trim();

	it.each(Object.entries(tokens.typography) as [string, Record<string, string>][])(
		'%s matches size, weight, line-height and tracking',
		(name, token) => {
			const block = utility(name);
			expect(block, `missing @utility type-${name}`).not.toBe('');
			const size = parseFloat(token.fontSize);
			expect(first(block, 'font-size')).toBe(`${size}px`);
			expect(Number(first(block, 'font-weight'))).toBe(Number(token.fontWeight));
			expect(Number(first(block, 'line-height'))).toBeCloseTo(Number(token.lineHeight), 5);
			// Tracking is stored in em so the percentage survives responsive size steps.
			const em = parseFloat(first(block, 'letter-spacing')!);
			expect(em).toBeCloseTo(parseFloat(token.letterSpacing) / size, 3);
		}
	);

	it('keeps the OpenType character variants the body voice depends on', () => {
		const features = /font-feature-settings:([^;]+);/.exec(css)![1];
		for (const tag of ['cv01', 'cv05', 'cv09', 'cv11', 'ss03', 'ss07', 'dlig']) {
			expect(features).toContain(`'${tag}'`);
		}
	});
});

/** WCAG 2.x relative luminance and contrast ratio. */
function luminance(hex: string): number {
	const [r, g, b] = [1, 3, 5]
		.map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
		.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a: string, b: string) => {
	const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
};
const c = tokens.colors as Record<string, string>;

describe('contrast of the pairings the UI uses', () => {
	const text: [string, string, string][] = [
		['ink', 'canvas', 'body text on the page'],
		['ink', 'surface-1', 'text on cards'],
		['ink', 'surface-2', 'text on featured cards, rows and popovers'],
		['ink-muted', 'canvas', 'secondary text on the page'],
		['ink-muted', 'surface-1', 'secondary text on cards'],
		['ink-muted', 'surface-2', 'secondary text on rows and popovers'],
		['on-primary', 'primary', 'white pill buttons'],
		['accent-blue', 'canvas', 'hyperlinks'],
		['accent-blue', 'surface-1', 'hyperlinks on cards'],
		['semantic-success', 'canvas', 'positive values'],
		['semantic-success', 'surface-1', 'positive values on cards'],
		['semantic-success', 'surface-2', 'success badges'],
		['gradient-coral', 'canvas', 'negative values'],
		['gradient-coral', 'surface-1', 'negative values on cards'],
		['gradient-coral', 'surface-2', 'error badges'],
		['ink', 'gradient-violet', 'text on the violet spotlight (lightest stop)'],
		['on-primary', 'gradient-orange', 'text on the orange spotlight (lightest stop)']
	];
	it.each(text)('%s on %s reaches 4.5:1 (%s)', (fg, bg) => {
		expect(contrast(c[fg], c[bg])).toBeGreaterThanOrEqual(4.5);
	});

	it.each([
		['accent-blue', 'canvas', 'focus ring'],
		['accent-blue', 'surface-2', 'focus ring on rows'],
		['gradient-violet', 'surface-1', 'chart series'],
		['gradient-orange', 'surface-1', 'chart series'],
		['gradient-magenta', 'surface-1', 'chart series'],
		['ink-muted', 'surface-1', 'chart axis']
	])('%s on %s reaches 3:1 for graphics (%s)', (fg, bg) => {
		expect(contrast(c[fg], c[bg])).toBeGreaterThanOrEqual(3);
	});
});
