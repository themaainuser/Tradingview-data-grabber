import { afterEach, describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page, userEvent } from 'vitest/browser';
import ThemeToggleHarness from '$lib/testing/ThemeToggleHarness.svelte';
import { AppState } from '$lib/state/app.svelte';
import { THEME_STORAGE_KEY, type ThemeEnv } from '$lib/state/theme.svelte';

const root = document.documentElement;

afterEach(() => {
	localStorage.removeItem(THEME_STORAGE_KEY);
	root.removeAttribute('data-theme');
	root.style.colorScheme = '';
});

/** The real browser (storage, matchMedia, DOM) with the OS appearance under the test's control. */
function mountToggle(
	options: { stored?: string; prefersDark?: boolean; variant?: 'icon' | 'labelled' } = {}
) {
	if (options.stored) localStorage.setItem(THEME_STORAGE_KEY, options.stored);
	const app = new AppState();
	const listeners = new Set<(event: { matches: boolean }) => void>();
	const query = {
		matches: options.prefersDark ?? true,
		addEventListener: (_: 'change', fn: (event: { matches: boolean }) => void) => listeners.add(fn),
		removeEventListener: (_: 'change', fn: (event: { matches: boolean }) => void) =>
			listeners.delete(fn)
	};
	const env: ThemeEnv = {
		window: {
			localStorage,
			matchMedia: () => query,
			getComputedStyle: (element) => getComputedStyle(element as Element),
			addEventListener: (type, fn) => window.addEventListener(type, fn as unknown as EventListener),
			removeEventListener: (type, fn) =>
				window.removeEventListener(type, fn as unknown as EventListener)
		},
		document
	};
	const detach = app.theme.attach(env);
	render(ThemeToggleHarness, { app, variant: options.variant ?? 'icon' });
	return {
		app,
		detach,
		setSystemDark(matches: boolean) {
			query.matches = matches;
			for (const fn of listeners) fn({ matches });
		}
	};
}

const radio = (name: string) => page.getByRole('radio', { name });
const checked = () =>
	['System', 'Dark', 'Light'].filter(
		(name) => radio(name).element().getAttribute('aria-checked') === 'true'
	);
const canvas = () => getComputedStyle(document.body).backgroundColor;

describe('ThemeToggle', () => {
	it('is a labelled radiogroup with System, Dark and Light, following the system by default', async () => {
		mountToggle();
		await expect.element(page.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
		expect(page.getByRole('radio').elements()).toHaveLength(3);
		expect(checked()).toEqual(['System']);
		// Each segment has an accessible name and a tooltip.
		for (const [name, title] of [
			['System', 'System theme'],
			['Dark', 'Dark theme'],
			['Light', 'Light theme']
		]) {
			expect(radio(name).element().getAttribute('title')).toContain(title);
		}
	});

	it('selects on click, applies the theme, and persists the choice', async () => {
		mountToggle({ prefersDark: true });
		await radio('Light').click();
		expect(checked()).toEqual(['Light']);
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(root.style.colorScheme).toBe('light');
		expect(canvas()).toBe('rgb(250, 250, 250)');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

		await radio('Dark').click();
		expect(checked()).toEqual(['Dark']);
		expect(root.getAttribute('data-theme')).toBe('dark');
		expect(canvas()).toBe('rgb(9, 9, 9)');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

		await radio('System').click();
		expect(checked()).toEqual(['System']);
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
		// prefersDark is true in this scenario, so System resolves to dark.
		expect(root.getAttribute('data-theme')).toBe('dark');
	});

	it('keeps only the selected radio in the tab order (roving tabindex)', async () => {
		mountToggle({ stored: 'dark' });
		expect(radio('Dark').element().getAttribute('tabindex')).toBe('0');
		expect(radio('System').element().getAttribute('tabindex')).toBe('-1');
		expect(radio('Light').element().getAttribute('tabindex')).toBe('-1');
		await radio('Light').click();
		expect(radio('Light').element().getAttribute('tabindex')).toBe('0');
		expect(radio('Dark').element().getAttribute('tabindex')).toBe('-1');
	});

	it('moves the selection and focus with the arrow keys, wrapping at the ends', async () => {
		mountToggle({ stored: 'system' });
		radio('System').element().focus();
		await userEvent.keyboard('{ArrowRight}');
		expect(checked()).toEqual(['Dark']);
		expect(document.activeElement).toBe(radio('Dark').element());
		await userEvent.keyboard('{ArrowDown}');
		expect(checked()).toEqual(['Light']);
		await userEvent.keyboard('{ArrowRight}');
		expect(checked()).toEqual(['System']);
		await userEvent.keyboard('{ArrowLeft}');
		expect(checked()).toEqual(['Light']);
		expect(document.activeElement).toBe(radio('Light').element());
		await userEvent.keyboard('{ArrowUp}');
		expect(checked()).toEqual(['Dark']);
		await userEvent.keyboard('{Home}');
		expect(checked()).toEqual(['System']);
		await userEvent.keyboard('{End}');
		expect(checked()).toEqual(['Light']);
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
	});

	it('shows a visible focus ring on keyboard focus', async () => {
		mountToggle({ stored: 'dark' });
		await userEvent.tab();
		expect(document.activeElement).toBe(radio('Dark').element());
		const shadow = getComputedStyle(radio('Dark').element()).boxShadow;
		expect(shadow).not.toBe('none');
		expect(shadow).toContain('rgb(0, 153, 255)');
	});

	it('restores a saved preference on the next visit', async () => {
		mountToggle({ stored: 'light', prefersDark: true });
		expect(checked()).toEqual(['Light']);
		expect(canvas()).toBe('rgb(250, 250, 250)');
	});

	it('reflects a live system change while on System, and ignores it while pinned', async () => {
		const { setSystemDark } = mountToggle({ prefersDark: true });
		expect(root.getAttribute('data-theme')).toBe('dark');
		setSystemDark(false);
		expect(checked()).toEqual(['System']);
		expect(root.getAttribute('data-theme')).toBe('light');
		expect(canvas()).toBe('rgb(250, 250, 250)');

		await radio('Dark').click();
		setSystemDark(false);
		setSystemDark(true);
		setSystemDark(false);
		expect(root.getAttribute('data-theme')).toBe('dark');
	});

	it('follows a preference written by another tab', async () => {
		mountToggle({ stored: 'dark' });
		window.dispatchEvent(
			new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'light' })
		);
		await expect.poll(checked).toEqual(['Light']);
		expect(root.getAttribute('data-theme')).toBe('light');
	});

	it('does not shift the layout when the selection changes, and moves the selection in 150 ms or less', async () => {
		mountToggle({ stored: 'system' });
		const group = page.getByRole('radiogroup', { name: 'Theme' }).element();
		const before = group.getBoundingClientRect();
		await radio('Light').click();
		const after = group.getBoundingClientRect();
		expect([after.width, after.height]).toEqual([before.width, before.height]);
		const thumb = group.querySelector('span[aria-hidden="true"]') as HTMLElement;
		const duration = parseFloat(getComputedStyle(thumb).transitionDuration);
		expect(duration).toBeGreaterThan(0);
		expect(duration).toBeLessThanOrEqual(0.15);
		// Transform only: a width or left transition would reflow.
		const properties = getComputedStyle(thumb).transitionProperty;
		expect(properties).toContain('transform');
		expect(properties).not.toMatch(/all|width|left/);
	});

	it('shows the word beside each icon in the labelled variant', async () => {
		mountToggle({ variant: 'labelled' });
		for (const name of ['System', 'Dark', 'Light']) {
			expect(radio(name).element().textContent?.trim()).toBe(name);
			expect(radio(name).element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
		}
		await radio('Dark').click();
		expect(checked()).toEqual(['Dark']);
	});
});
