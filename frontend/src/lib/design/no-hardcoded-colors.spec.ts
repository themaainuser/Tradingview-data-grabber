/**
 * Components never hard-code colour: a literal (or a utility that is always black or white) looks
 * right in one theme and breaks in the other. Literals belong in src/routes/layout.css, where the
 * tokens are declared per theme (and in app.html, whose pre-paint values theme.spec.ts checks
 * against those tokens).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = fileURLToPath(new URL('../../', import.meta.url));

const walk = (dir: string): string[] =>
	readdirSync(dir).flatMap((name) => {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) return walk(path);
		return /\.(svelte|ts)$/.test(name) && !/\.spec\.ts$/.test(name) ? [path] : [];
	});

/** Files (relative to src/) that may break a rule, with the rule name and the reason. Empty on purpose. */
const ALLOWED: Record<string, { rule: string; why: string }[]> = {};

const RULES: Record<string, RegExp> = {
	'hex colour literal': /#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b(?![\w-])/g,
	'rgb()/hsl() literal': /\b(?:rgba?|hsla?|oklch|oklab)\(\s*[\d.]/g,
	'always-black/white utility':
		/\b(?:bg|text|border|ring|fill|stroke|from|to|via|outline|divide|shadow|decoration)-(?:white|black)\b|\b(?:white|black)\/\d/g,
	// The vivid brand colours are fills: as text they are 2-3:1 on the light canvas. Text uses the *-ink tokens.
	'vivid brand colour as text': /\btext-(?:gradient-[a-z]+|success)(?![\w-])/g
};

const sources = walk(root).map((file) => ({
	file: file.slice(root.length),
	text: readFileSync(file, 'utf8')
}));

describe('no hard-coded colours outside layout.css', () => {
	it('finds the sources it is meant to guard', () => {
		expect(sources.length).toBeGreaterThan(100);
		expect(sources.some((s) => s.file === 'lib/components/app/ThemeToggle.svelte')).toBe(true);
	});

	it.each(Object.entries(RULES))('no source uses a %s', (name, pattern) => {
		const offenders = sources.flatMap(({ file, text }) => {
			if (ALLOWED[file]?.some((a) => a.rule === name)) return [];
			const hits = [...text.matchAll(pattern)].map((m) => m[0]);
			return hits.length ? [`${file}: ${[...new Set(hits)].join(', ')}`] : [];
		});
		expect(offenders).toEqual([]);
	});

	it('rule patterns catch what they exist for and ignore what they should', () => {
		const hit = (rule: string, text: string) => new RegExp(RULES[rule]).test(text);
		expect(hit('hex colour literal', 'fill="#fff"')).toBe(true);
		expect(hit('hex colour literal', 'style="color: #0099ff"')).toBe(true);
		expect(hit('hex colour literal', 'href="#indicators"')).toBe(false);
		expect(hit('always-black/white utility', 'class="bg-white/10"')).toBe(true);
		expect(hit('always-black/white utility', 'class="text-white"')).toBe(true);
		expect(hit('rgb()/hsl() literal', 'rgb(255 85 119 / 0.5)')).toBe(true);
		expect(hit('vivid brand colour as text', 'class="text-gradient-coral"')).toBe(true);
		expect(hit('vivid brand colour as text', 'class="text-success-ink"')).toBe(false);
	});
});
