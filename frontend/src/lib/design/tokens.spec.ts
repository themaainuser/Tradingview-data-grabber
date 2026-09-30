/**
 * Keeps the implementation honest against frontend/DESIGN.md (the design source of truth):
 * every color, spacing, radius and type token in its front matter must exist in layout.css with
 * the same value, and every text/background pairing the UI uses must meet WCAG contrast.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
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
const lightBlock = /:root\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/.exec(css)![1];
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

describe('light palette (colors-light)', () => {
	const light = tokens['colors-light'] as Record<string, string>;

	it('is parsed from the front matter', () => {
		expect(Object.keys(light).length).toBeGreaterThanOrEqual(14);
	});
	it.each(Object.entries(light))('%s is declared in :root[data-theme=light]', (name, value) => {
		expect(declared(lightBlock, name)).toBe(value.toLowerCase());
	});
	it('only overrides tokens that exist in the dark palette, under the same names', () => {
		for (const name of Object.keys(light)) expect(tokens.colors, name).toHaveProperty(name);
	});
	it('declares nothing in the light block that DESIGN.md does not list', () => {
		const names = [...lightBlock.matchAll(/^\s*--([\w-]+):/gm)].map((m) => m[1]);
		// Derived, non-hex tokens are allowed; hex-valued ones must be documented.
		const hexNames = names.filter((n) => /^#[0-9a-f]{3,8}$/i.test(declared(lightBlock, n) ?? ''));
		expect(hexNames.filter((n) => !(n in light))).toEqual([]);
	});
	it('sets color-scheme per theme', () => {
		expect(rootBlock).toMatch(/color-scheme:\s*dark;/);
		expect(lightBlock).toMatch(/color-scheme:\s*light;/);
	});
	it('makes the vendored dark: variant follow the attribute instead of always applying', () => {
		expect(css).toContain(
			"@custom-variant dark (&:where([data-theme='dark'], [data-theme='dark'] *));"
		);
		expect(css).not.toContain('@custom-variant dark (&:where(*))');
	});
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
/** `fg` at `alpha` composited over opaque `bg` (Tailwind's `bg-ink/10`, `border-ink-muted/75`...). */
const over = (fg: string, bg: string, alpha: number) =>
	'#' +
	[1, 3, 5]
		.map((i) =>
			Math.round(
				alpha * parseInt(fg.slice(i, i + 2), 16) + (1 - alpha) * parseInt(bg.slice(i, i + 2), 16)
			)
				.toString(16)
				.padStart(2, '0')
		)
		.join('');

const palettes = {
	dark: tokens.colors as Record<string, string>,
	// Tokens the light block does not override (gradients, spotlight inks, success) are inherited.
	light: {
		...(tokens.colors as Record<string, string>),
		...(tokens['colors-light'] as Record<string, string>)
	}
};

describe.each(Object.entries(palettes))(
	'contrast of the pairings the UI uses (%s)',
	(_theme, c) => {
		const text: [string, string, string][] = [
			['ink', 'canvas', 'body text on the page'],
			['ink', 'surface-1', 'text on cards'],
			['ink', 'surface-2', 'text on featured cards, rows and popovers'],
			['ink-muted', 'canvas', 'secondary text on the page'],
			['ink-muted', 'surface-1', 'secondary text on cards and placeholder text in fields'],
			['ink-muted', 'surface-2', 'secondary text on rows, popovers and badges'],
			['on-primary', 'primary', 'primary pill buttons'],
			['accent-blue', 'canvas', 'hyperlinks'],
			['accent-blue', 'surface-1', 'hyperlinks on cards'],
			['accent-blue', 'surface-2', 'hyperlinks on rows and popovers'],
			['success-ink', 'canvas', 'positive values'],
			['success-ink', 'surface-1', 'positive values on cards'],
			['success-ink', 'surface-2', 'success badges'],
			['coral-ink', 'canvas', 'negative values and errors'],
			['coral-ink', 'surface-1', 'negative values on cards, destructive buttons'],
			['coral-ink', 'surface-2', 'error badges'],
			['orange-ink', 'canvas', 'fear band names'],
			['orange-ink', 'surface-1', 'fear band names on cards'],
			['orange-ink', 'surface-2', 'fear band names on the highlighted card'],
			['spotlight-ink-white', 'gradient-violet', 'text on the violet spotlight (lightest stop)'],
			['spotlight-ink-black', 'gradient-orange', 'text on the orange spotlight (lightest stop)']
		];
		it.each(text)('%s on %s reaches 4.5:1 (%s)', (fg, bg) => {
			expect(contrast(c[fg], c[bg])).toBeGreaterThanOrEqual(4.5);
		});

		it.each([
			['accent-blue', 'canvas', 'focus ring'],
			['accent-blue', 'surface-1', 'focus ring on cards'],
			['accent-blue', 'surface-2', 'focus ring on rows'],
			['gradient-violet', 'surface-1', 'chart series'],
			['orange-ink', 'surface-1', 'chart series'],
			['magenta-ink', 'surface-1', 'chart series'],
			['success-ink', 'surface-1', 'candles up and sign-coloured bars'],
			['coral-ink', 'surface-1', 'candles down and sign-coloured bars'],
			['ink', 'surface-1', 'chart series, gauge needle'],
			['ink-muted', 'surface-1', 'chart axis and neutral band'],
			['primary', 'canvas', 'primary pill and the selected theme segment'],
			['primary', 'surface-1', 'primary pill inside cards, selected switch and checkbox']
		])('%s on %s reaches 3:1 for graphics (%s)', (fg, bg) => {
			expect(contrast(c[fg], c[bg])).toBeGreaterThanOrEqual(3);
		});

		it('keeps ink legible on the hover overlays (bg-ink/10 on ghost buttons, menu items, command rows)', () => {
			for (const ground of ['canvas', 'surface-1', 'surface-2']) {
				const hovered = over(c.ink, c[ground], 0.1);
				expect(contrast(c.ink, hovered), `ink on hovered ${ground}`).toBeGreaterThanOrEqual(4.5);
			}
		});

		it('keeps the checkbox edge (ink-muted at 75%) at 3:1 on canvas and cards', () => {
			const edge = (ground: string) => over(c['ink-muted'], c[ground], 0.75);
			expect(contrast(edge('canvas'), c.canvas)).toBeGreaterThanOrEqual(3);
			expect(contrast(edge('surface-1'), c['surface-1'])).toBeGreaterThanOrEqual(3);
		});
	}
);

describe('the light palette', () => {
	const { dark, light } = palettes;
	it('is a different palette that keeps the dark one intact', () => {
		expect(light.canvas).not.toBe(dark.canvas);
		expect(luminance(light.canvas)).toBeGreaterThan(luminance(dark.canvas));
		expect(luminance(light.ink)).toBeLessThan(luminance(light.canvas));
		expect(dark.canvas).toBe('#090909');
		expect(dark.ink).toBe('#ffffff');
	});
	it('keeps the surface lift monotonic away from the canvas', () => {
		expect(luminance(light.canvas)).toBeGreaterThan(luminance(light['surface-1']));
		expect(luminance(light['surface-1'])).toBeGreaterThan(luminance(light['surface-2']));
		expect(luminance(dark.canvas)).toBeLessThan(luminance(dark['surface-1']));
		expect(luminance(dark['surface-1'])).toBeLessThan(luminance(dark['surface-2']));
	});
	it('needs its darker text variants: the vivid brand colours fail as text on the light canvas', () => {
		for (const [vivid, ink] of [
			['semantic-success', 'success-ink'],
			['gradient-coral', 'coral-ink'],
			['gradient-orange', 'orange-ink']
		]) {
			expect(contrast(light[vivid], light.canvas), vivid).toBeLessThan(4.5);
			expect(contrast(light[ink], light.canvas), ink).toBeGreaterThanOrEqual(4.5);
		}
	});
});

/**
 * DESIGN.md names spacing steps (xs, md, lg...), but only Tailwind's numeric scale and arbitrary
 * values generate utilities here. A class like `gap-md` compiles to nothing and silently drops
 * the gap, so no source file may use one.
 */
describe('spacing utilities', () => {
	const walk = (dir: string): string[] =>
		readdirSync(dir).flatMap((name) => {
			const path = join(dir, name);
			if (statSync(path).isDirectory()) return walk(path);
			return /\.(svelte|ts)$/.test(name) && !/\.spec\.ts$/.test(name) ? [path] : [];
		});
	const root = fileURLToPath(new URL('../../', import.meta.url));
	const named =
		/(?:^|[\s"'`{:])-?(?:gap|gap-x|gap-y|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|space-x|space-y)-(?:hair|xxs|xs|sm|md|lg|xl|xxl|section)(?=[\s"'`}:]|$)/;

	it('never uses a named spacing step that generates no CSS', () => {
		const offenders = walk(root).filter((file) => named.test(readFileSync(file, 'utf8')));
		expect(offenders.map((f) => f.slice(root.length))).toEqual([]);
	});
});
