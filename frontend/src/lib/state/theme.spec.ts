import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';
import {
	THEME_STORAGE_KEY,
	ThemeStore,
	parsePreference,
	resolveTheme,
	type Theme,
	type ThemeEnv
} from './theme.svelte';

const read = (relative: string) =>
	readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const css = read('../../routes/layout.css');
const appHtml = read('../../app.html');

const canvasOf = (block: string) => /--canvas:\s*(#[0-9a-f]{6});/i.exec(block)![1].toLowerCase();
const CANVAS: Record<Theme, string> = {
	dark: canvasOf(/:root\s*\{([\s\S]*?)\n\}/.exec(css)![1]),
	light: canvasOf(/:root\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/.exec(css)![1])
};

interface Setup {
	/** Stored value; `'throw'` makes every storage access throw (private mode, blocked cookies). */
	stored?: string | null | 'throw';
	prefersDark?: boolean;
	writeThrows?: boolean;
	matchMedia?: 'ok' | 'missing';
	canvas?: Record<Theme, string>;
}

/** A browser in a box: records every DOM write so tests can assert on effects, not just state. */
function fakeBrowser({
	stored = null,
	prefersDark = false,
	writeThrows = false,
	matchMedia = 'ok',
	canvas = CANVAS
}: Setup = {}) {
	const attrs = new Map<string, string>();
	const writes: string[] = [];
	const root = {
		style: { colorScheme: '' },
		getAttribute: (name: string) => attrs.get(name) ?? null,
		setAttribute: (name: string, value: string) => {
			attrs.set(name, value);
			writes.push(`${name}=${value}`);
		}
	};
	const meta = {
		content: '#090909',
		setAttribute(name: string, value: string) {
			if (name === 'content') this.content = value;
		}
	};
	let value = stored;
	const storage = {
		sets: 0,
		getItem: (key: string) => {
			if (value === 'throw') throw new Error('SecurityError');
			return key === THEME_STORAGE_KEY ? value : null;
		},
		setItem: (key: string, next: string) => {
			if (writeThrows || value === 'throw') throw new Error('QuotaExceededError');
			storage.sets++;
			if (key === THEME_STORAGE_KEY) value = next;
		}
	};
	const queryListeners = new Set<(event: { matches: boolean }) => void>();
	const query = {
		matches: prefersDark,
		addEventListener: (_: 'change', fn: (event: { matches: boolean }) => void) =>
			queryListeners.add(fn),
		removeEventListener: (_: 'change', fn: (event: { matches: boolean }) => void) =>
			queryListeners.delete(fn)
	};
	const storageListeners = new Set<
		(event: { key: string | null; newValue: string | null }) => void
	>();
	const env: ThemeEnv = {
		window: {
			localStorage: storage,
			matchMedia: () => {
				if (matchMedia === 'missing') throw new TypeError('matchMedia is not a function');
				return query;
			},
			getComputedStyle: () => ({
				getPropertyValue: (name: string) =>
					name === '--canvas' ? canvas[attrs.get('data-theme') === 'light' ? 'light' : 'dark'] : ''
			}),
			addEventListener: (_: 'storage', fn) => storageListeners.add(fn),
			removeEventListener: (_: 'storage', fn) => storageListeners.delete(fn)
		},
		document: { documentElement: root, querySelector: () => meta }
	};
	return {
		env,
		root,
		meta,
		storage,
		writes,
		get stored() {
			return value;
		},
		/** The OS flips its appearance setting. */
		setSystemDark(matches: boolean) {
			query.matches = matches;
			for (const fn of [...queryListeners]) fn({ matches });
		},
		/** Another tab writes the preference (the `storage` event never fires in the writing tab). */
		fireStorage(event: { key: string | null; newValue: string | null }) {
			for (const fn of [...storageListeners]) fn(event);
		},
		listeners: () => ({ query: queryListeners.size, storage: storageListeners.size })
	};
}

function mount(setup?: Setup) {
	const browser = fakeBrowser(setup);
	const store = new ThemeStore();
	const detach = store.attach(browser.env);
	// Object.assign keeps the `stored` getter live (a spread would freeze it).
	return Object.assign(browser, { store, detach });
}

/** The contract, written out by hand rather than via resolveTheme so it cannot share a bug with it. */
const expectedTheme = (stored: string | null | 'throw', prefersDark: boolean): Theme =>
	stored === 'dark' ? 'dark' : stored === 'light' ? 'light' : prefersDark ? 'dark' : 'light';

const STORED: (string | null | 'throw')[] = [
	null,
	'system',
	'dark',
	'light',
	'',
	'Dark',
	'auto',
	'null',
	'{"theme":"dark"}',
	'throw'
];

describe('resolution', () => {
	it('parses only the three known values and falls back to system for everything else', () => {
		expect(['system', 'dark', 'light'].map(parsePreference)).toEqual(['system', 'dark', 'light']);
		for (const bad of [null, undefined, '', 'Dark', 'auto', 0, {}, 'light ']) {
			expect(parsePreference(bad), String(bad)).toBe('system');
		}
	});
	it('pins dark and light regardless of the system and follows it for system', () => {
		expect(resolveTheme('dark', false)).toBe('dark');
		expect(resolveTheme('light', true)).toBe('light');
		expect(resolveTheme('system', true)).toBe('dark');
		expect(resolveTheme('system', false)).toBe('light');
	});
});

describe('ThemeStore', () => {
	it('is constructed without touching the browser and defaults to system / dark', () => {
		expect(typeof window).toBe('undefined');
		const store = new ThemeStore();
		expect(store.preference).toBe('system');
		expect(store.resolved).toBe('dark');
	});

	describe.each(STORED)('stored %j', (stored) => {
		it.each([true, false])(
			'applies the expected theme when the system prefers dark = %s',
			(dark) => {
				const { store, root, meta } = mount({ stored, prefersDark: dark });
				const theme = expectedTheme(stored, dark);
				expect(store.resolved).toBe(theme);
				expect(root.getAttribute('data-theme')).toBe(theme);
				expect(root.style.colorScheme).toBe(theme);
				expect(meta.content).toBe(CANVAS[theme]);
			}
		);
	});

	it('reads an invalid stored value as system, and does not rewrite it', () => {
		const { store, storage } = mount({ stored: 'sepia', prefersDark: false });
		expect(store.preference).toBe('system');
		expect(store.resolved).toBe('light');
		expect(storage.sets).toBe(0);
	});

	it('persists a chosen preference and applies it immediately', () => {
		const browser = mount({ prefersDark: true });
		browser.store.set('light');
		expect(browser.stored).toBe('light');
		expect(browser.store.resolved).toBe('light');
		expect(browser.root.getAttribute('data-theme')).toBe('light');
		expect(browser.root.style.colorScheme).toBe('light');
		browser.store.set('system');
		expect(browser.stored).toBe('system');
		expect(browser.root.getAttribute('data-theme')).toBe('dark');
	});

	it('restores the saved preference on the next visit', () => {
		const first = mount({ prefersDark: true });
		first.store.set('light');
		const second = mount({ stored: first.stored, prefersDark: true });
		expect(second.store.preference).toBe('light');
		expect(second.root.getAttribute('data-theme')).toBe('light');
	});

	it('keeps working when storage throws on read and on write', () => {
		const blocked = mount({ stored: 'throw', prefersDark: false });
		expect(blocked.store.preference).toBe('system');
		expect(blocked.store.resolved).toBe('light');
		expect(() => blocked.store.set('dark')).not.toThrow();
		expect(blocked.store.resolved).toBe('dark');
		expect(blocked.root.getAttribute('data-theme')).toBe('dark');

		const full = mount({ writeThrows: true, prefersDark: true });
		expect(() => full.store.set('light')).not.toThrow();
		expect(full.root.getAttribute('data-theme')).toBe('light');
	});

	it('ignores an unknown value passed to set()', () => {
		const { store, root } = mount({ prefersDark: true });
		store.set('sepia' as never);
		expect(store.preference).toBe('system');
		expect(root.getAttribute('data-theme')).toBe('dark');
	});

	describe('system changes', () => {
		it('follows a live OS change while the preference is system', () => {
			const { store, root, meta, setSystemDark } = mount({ prefersDark: true });
			expect(store.resolved).toBe('dark');
			setSystemDark(false);
			expect(store.resolved).toBe('light');
			expect(root.getAttribute('data-theme')).toBe('light');
			expect(root.style.colorScheme).toBe('light');
			expect(meta.content).toBe(CANVAS.light);
			setSystemDark(true);
			expect(root.getAttribute('data-theme')).toBe('dark');
			expect(meta.content).toBe(CANVAS.dark);
		});

		it.each(['dark', 'light'] as const)(
			'does not move a pinned %s preference, and does not touch the DOM',
			(pinned) => {
				const { store, root, writes, setSystemDark } = mount({
					stored: pinned,
					prefersDark: pinned === 'dark'
				});
				const before = writes.length;
				setSystemDark(pinned !== 'dark');
				expect(store.resolved).toBe(pinned);
				expect(root.getAttribute('data-theme')).toBe(pinned);
				expect(writes.length).toBe(before);
			}
		);

		it('uses the latest system value when a pinned preference goes back to system', () => {
			const { store, root, setSystemDark } = mount({ stored: 'dark', prefersDark: true });
			setSystemDark(false);
			expect(root.getAttribute('data-theme')).toBe('dark');
			store.set('system');
			expect(root.getAttribute('data-theme')).toBe('light');
		});

		it('defaults to dark when matchMedia is unavailable', () => {
			const { store, root } = mount({ matchMedia: 'missing' });
			expect(store.resolved).toBe('dark');
			expect(root.getAttribute('data-theme')).toBe('dark');
		});
	});

	describe('other tabs', () => {
		it('adopts a preference written by another tab without writing it back', () => {
			const { store, root, storage, fireStorage } = mount({ prefersDark: true });
			fireStorage({ key: THEME_STORAGE_KEY, newValue: 'light' });
			expect(store.preference).toBe('light');
			expect(root.getAttribute('data-theme')).toBe('light');
			expect(storage.sets).toBe(0);
			fireStorage({ key: THEME_STORAGE_KEY, newValue: 'system' });
			expect(store.preference).toBe('system');
			expect(root.getAttribute('data-theme')).toBe('dark');
		});
		it('ignores other keys, and reads a cleared or corrupt value as system', () => {
			const { store, fireStorage } = mount({ stored: 'light', prefersDark: true });
			fireStorage({ key: 'something-else', newValue: 'dark' });
			expect(store.preference).toBe('light');
			fireStorage({ key: THEME_STORAGE_KEY, newValue: 'purple' });
			expect(store.preference).toBe('system');
			fireStorage({ key: THEME_STORAGE_KEY, newValue: 'dark' });
			fireStorage({ key: null, newValue: null });
			expect(store.preference).toBe('system');
		});
	});

	it('updates the theme-color meta from the canvas token of the new theme, and leaves it alone without CSS', () => {
		const { store, meta } = mount({ prefersDark: true });
		expect(meta.content).toBe(CANVAS.dark);
		store.set('light');
		expect(meta.content).toBe(CANVAS.light);
		store.set('dark');
		expect(meta.content).toBe(CANVAS.dark);

		const noCss = mount({ prefersDark: false, canvas: { dark: '', light: '' } });
		expect(noCss.meta.content).toBe('#090909');
	});

	it('stops listening when detached', () => {
		const { store, detach, listeners, setSystemDark, fireStorage, root } = mount({
			prefersDark: true
		});
		expect(listeners()).toEqual({ query: 1, storage: 1 });
		detach();
		expect(listeners()).toEqual({ query: 0, storage: 0 });
		setSystemDark(false);
		fireStorage({ key: THEME_STORAGE_KEY, newValue: 'light' });
		expect(root.getAttribute('data-theme')).toBe('dark');
		expect(store.preference).toBe('system');
	});
});

describe('app.html pre-paint script', () => {
	const script = /<script>([\s\S]*?)<\/script>/.exec(appHtml)?.[1];

	/** Runs the script text from app.html in a sandbox that stubs only what a browser provides. */
	function runScript({ stored = null, prefersDark = false, matchMedia = 'ok' }: Setup) {
		const attrs = new Map<string, string>();
		const meta = { content: '#090909', setAttribute: (_: string, v: string) => (meta.content = v) };
		const root = {
			style: { colorScheme: '' },
			setAttribute: (name: string, value: string) => attrs.set(name, value)
		};
		const sandbox: Record<string, unknown> = {
			document: {
				documentElement: root,
				querySelector: (selector: string) => (selector.includes('theme-color') ? meta : null)
			},
			matchMedia: (query: string) => {
				if (matchMedia === 'missing') throw new TypeError('matchMedia is not a function');
				return { matches: query === '(prefers-color-scheme: dark)' && prefersDark };
			}
		};
		Object.defineProperty(sandbox, 'localStorage', {
			get() {
				if (stored === 'throw') throw new Error('SecurityError');
				return { getItem: (key: string) => (key === THEME_STORAGE_KEY ? stored : null) };
			}
		});
		vm.runInNewContext(script!, sandbox);
		return {
			theme: attrs.get('data-theme'),
			colorScheme: root.style.colorScheme,
			meta: meta.content
		};
	}

	it('is a synchronous classic script in <head>, before the SvelteKit head', () => {
		expect(script).toBeTruthy();
		const head = appHtml.slice(appHtml.indexOf('<head>'), appHtml.indexOf('</head>'));
		expect(head).toContain(script!);
		expect(head.indexOf('<script>')).toBeLessThan(head.indexOf('%sveltekit.head%'));
		expect(head.indexOf('theme-color')).toBeLessThan(head.indexOf('<script>'));
		expect(appHtml.match(/<script\b[^>]*>/g)).toEqual(['<script>']);
	});

	it('does not hard-code a dark <html> any more', () => {
		expect(appHtml).toMatch(/<html lang="en">/);
		expect(appHtml).not.toMatch(/<html[^>]*style=/);
	});

	describe.each(STORED)('stored %j', (stored) => {
		it.each([true, false])(
			'resolves exactly like ThemeStore when the system prefers dark = %s',
			(prefersDark) => {
				const fromScript = runScript({ stored, prefersDark });
				const fromStore = mount({ stored, prefersDark });
				const theme = expectedTheme(stored, prefersDark);
				expect(fromScript.theme).toBe(theme);
				expect(fromScript.theme).toBe(fromStore.root.getAttribute('data-theme'));
				expect(fromScript.colorScheme).toBe(fromStore.root.style.colorScheme);
				expect(fromScript.meta).toBe(fromStore.meta.content);
			}
		);
	});

	it('also agrees when matchMedia is unavailable', () => {
		for (const stored of [null, 'system', 'light', 'dark'] as const) {
			const fromScript = runScript({ stored, matchMedia: 'missing' });
			const fromStore = mount({ stored, matchMedia: 'missing' });
			expect(fromScript.theme, String(stored)).toBe(fromStore.root.getAttribute('data-theme'));
		}
	});

	it('writes theme-color literals and a pre-CSS ground that equal the --canvas tokens', () => {
		expect(runScript({ stored: 'dark' }).meta).toBe(CANVAS.dark);
		expect(runScript({ stored: 'light' }).meta).toBe(CANVAS.light);
		expect(appHtml).toContain(`<meta name="theme-color" content="${CANVAS.dark}" />`);
		const style = /<style>([\s\S]*?)<\/style>/.exec(appHtml)![1];
		expect(/^\s*html\s*\{[^}]*background:\s*(#[0-9a-f]{6})/im.exec(style)![1]).toBe(CANVAS.dark);
		expect(
			/html\[data-theme='light'\]\s*\{[^}]*background:\s*(#[0-9a-f]{6})/i.exec(style)![1]
		).toBe(CANVAS.light);
	});
});
