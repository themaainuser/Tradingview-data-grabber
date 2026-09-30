import { createSubscriber } from 'svelte/reactivity';

export type ThemePreference = 'system' | 'dark' | 'light';
/** What is actually rendered; `system` is only ever a preference. */
export type Theme = 'dark' | 'light';

export const THEME_STORAGE_KEY = 'tvdata-theme';
export const DARK_QUERY = '(prefers-color-scheme: dark)';
export const THEME_PREFERENCES: readonly ThemePreference[] = ['system', 'dark', 'light'];

/** Anything that is not one of the three known values falls back to following the system. */
export function parsePreference(raw: unknown): ThemePreference {
	return raw === 'dark' || raw === 'light' || raw === 'system' ? raw : 'system';
}

export function resolveTheme(preference: ThemePreference, systemDark: boolean): Theme {
	return preference === 'system' ? (systemDark ? 'dark' : 'light') : preference;
}

interface MediaQueryLike {
	readonly matches: boolean;
	addEventListener(type: 'change', listener: (event: { matches: boolean }) => void): void;
	removeEventListener(type: 'change', listener: (event: { matches: boolean }) => void): void;
}
interface StorageEventLike {
	readonly key: string | null;
	readonly newValue: string | null;
}

/** The slice of the browser the store touches; node tests pass fakes instead of stubbing globals. */
export interface ThemeEnv {
	window: {
		readonly localStorage: Pick<Storage, 'getItem' | 'setItem'>;
		matchMedia(query: string): MediaQueryLike;
		getComputedStyle(element: unknown): Pick<CSSStyleDeclaration, 'getPropertyValue'>;
		addEventListener(type: 'storage', listener: (event: StorageEventLike) => void): void;
		removeEventListener(type: 'storage', listener: (event: StorageEventLike) => void): void;
	};
	document: {
		readonly documentElement: {
			getAttribute(name: string): string | null;
			setAttribute(name: string, value: string): void;
			readonly style: { colorScheme: string };
		};
		querySelector(selector: string): { setAttribute(name: string, value: string): void } | null;
	};
}

const browserEnv = (): ThemeEnv => ({ window, document }) as unknown as ThemeEnv;

/**
 * Theme preference (system / dark / light) and the theme it resolves to. Part of AppState and
 * created without touching `window`; `attach()` (called from the root layout on mount) wires the
 * browser: stored preference, `prefers-color-scheme`, other tabs, and the `data-theme` attribute
 * on <html> that layout.css keys every token off.
 */
export class ThemeStore {
	preference = $state<ThemePreference>('system');
	#systemDark = $state(true);
	readonly resolved: Theme = $derived(resolveTheme(this.preference, this.#systemDark));
	#env: ThemeEnv | null = null;

	/** Reads storage and the OS setting, applies the theme and starts listening. Returns the teardown. */
	attach(env: ThemeEnv = browserEnv()): () => void {
		this.#env = env;
		this.preference = parsePreference(this.#read());

		let query: MediaQueryLike | null = null;
		try {
			query = env.window.matchMedia(DARK_QUERY);
			this.#systemDark = query.matches;
		} catch {
			this.#systemDark = true;
		}
		// Always tracked so that switching back to `system` is never stale; while pinned it cannot change `resolved`.
		const onQuery = (event: { matches: boolean }) => {
			this.#systemDark = event.matches;
			this.#apply();
		};
		const onStorage = (event: StorageEventLike) => {
			if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;
			this.preference = parsePreference(event.newValue);
			this.#apply();
		};
		query?.addEventListener('change', onQuery);
		env.window.addEventListener('storage', onStorage);
		this.#apply();

		return () => {
			query?.removeEventListener('change', onQuery);
			env.window.removeEventListener('storage', onStorage);
			if (this.#env === env) this.#env = null;
		};
	}

	set(preference: ThemePreference): void {
		this.preference = parsePreference(preference);
		try {
			this.#env?.window.localStorage.setItem(THEME_STORAGE_KEY, this.preference);
		} catch {
			// Private mode or a full quota: the choice still applies for this session.
		}
		this.#apply();
	}

	#read(): string | null {
		try {
			return this.#env?.window.localStorage.getItem(THEME_STORAGE_KEY) ?? null;
		} catch {
			return null;
		}
	}

	#apply(): void {
		const env = this.#env;
		if (!env) return;
		const theme = this.resolved;
		const root = env.document.documentElement;
		// Skipping a no-op write keeps canvas charts from repainting for nothing.
		if (root.getAttribute('data-theme') !== theme) root.setAttribute('data-theme', theme);
		root.style.colorScheme = theme;
		// Browser chrome follows the canvas token, so the literal lives in layout.css only.
		const canvas = env.window.getComputedStyle(root).getPropertyValue('--canvas').trim();
		if (canvas)
			env.document.querySelector('meta[name="theme-color"]')?.setAttribute('content', canvas);
	}
}

const subscribeRendered = createSubscriber((update) => {
	const observer = new MutationObserver(update);
	observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
	return () => observer.disconnect();
});

/**
 * The theme currently on <html>, reactive inside effects and deriveds. For code that needs the
 * resolved theme in JS (contrast maths) without being handed the store.
 */
export function renderedTheme(): Theme {
	subscribeRendered();
	return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}
