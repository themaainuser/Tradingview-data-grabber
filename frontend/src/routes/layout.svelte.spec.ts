import { createRawSnippet } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page, userEvent } from 'vitest/browser';
import { THEME_STORAGE_KEY } from '$lib/state/theme.svelte';
import Layout from './+layout.svelte';

// The layout reads the current route from SvelteKit; pin it to /research for the nav state.
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/research') } }));

const children = createRawSnippet(() => ({ render: () => '<p>page content</p>' }));

// Never depend on whatever is listening behind Vite's /api proxy: every test stubs the network.
const emptyBackend = () =>
	new Response(JSON.stringify({ datasets: [] }), {
		headers: { 'Content-Type': 'application/json' }
	});

describe('app shell', () => {
	beforeEach(() => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => emptyBackend())
		);
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		localStorage.removeItem(THEME_STORAGE_KEY);
		document.documentElement.removeAttribute('data-theme');
		document.documentElement.style.colorScheme = '';
	});

	it('renders the primary nav with the current section marked, and a primary Import CSV pill', async () => {
		await page.viewport(1280, 800);
		render(Layout, { children });
		const nav = page.getByRole('navigation', { name: 'Primary' });
		await expect.element(nav).toBeInTheDocument();
		await expect
			.element(nav.getByRole('link', { name: 'Research' }))
			.toHaveAttribute('aria-current', 'page');
		await expect.element(nav.getByRole('link', { name: 'Docs' })).toHaveAttribute('href', '/docs');
		await expect
			.element(nav.getByRole('link', { name: 'Providers' }))
			.toHaveAttribute('href', '/providers');
		await expect
			.element(nav.getByRole('link', { name: 'Datasets' }))
			.not.toHaveAttribute('aria-current');
		await expect.element(page.getByRole('button', { name: 'Import CSV' })).toBeInTheDocument();
		await expect.element(page.getByText('page content')).toBeInTheDocument();
	});

	it('follows the theme: the canvas differs per theme and <html> hard-codes no dark ground', async () => {
		await page.viewport(1280, 800);
		localStorage.setItem(THEME_STORAGE_KEY, 'dark');
		render(Layout, { children });
		const html = document.documentElement;
		await vi.waitFor(() => expect(html.getAttribute('data-theme')).toBe('dark'));
		expect(getComputedStyle(document.body).backgroundColor).toBe('rgb(9, 9, 9)');
		expect(getComputedStyle(html).colorScheme).toBe('dark');

		await page.getByRole('radio', { name: 'Light' }).click();
		expect(html.getAttribute('data-theme')).toBe('light');
		expect(getComputedStyle(document.body).backgroundColor).toBe('rgb(250, 250, 250)');
		expect(getComputedStyle(html).backgroundColor).toBe('rgb(250, 250, 250)');
		expect(getComputedStyle(html).colorScheme).toBe('light');
		expect(getComputedStyle(document.body).color).toBe('rgb(5, 5, 5)');
		// Only color-scheme may be inlined on <html>; a hard-coded background would pin one theme.
		expect(html.getAttribute('style') ?? '').not.toMatch(/background|#090909/);
	});

	it('puts the theme toggle in the desktop header, right after Import CSV', async () => {
		await page.viewport(1280, 800);
		render(Layout, { children });
		const group = page.getByRole('radiogroup', { name: 'Theme' });
		await expect.element(group).toBeVisible();
		const imports = page.getByRole('button', { name: 'Import CSV' }).element();
		expect(imports.nextElementSibling).toBe(group.element());
		expect(group.element().closest('header')).not.toBeNull();
		expect(page.getByRole('radio').elements()).toHaveLength(3);
	});

	it('follows the system when nothing is stored, and a stored choice wins over it', async () => {
		await page.viewport(1280, 800);
		localStorage.setItem(THEME_STORAGE_KEY, 'light');
		render(Layout, { children });
		await vi.waitFor(() =>
			expect(
				page.getByRole('radio', { name: 'Light' }).element().getAttribute('aria-checked')
			).toBe('true')
		);
		expect(document.documentElement.getAttribute('data-theme')).toBe('light');
	});

	it('reports an unreachable backend instead of pretending it is connected', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
		render(Layout, { children });
		// The client retries with backoff before giving up.
		await vi.waitFor(() => expect(document.body.textContent).toContain('Backend unreachable'), {
			timeout: 5000
		});
		expect(document.body.textContent).not.toContain('Backend connected');
	});

	it('shows the dataset count once the backend answers', async () => {
		render(Layout, { children });
		await vi.waitFor(() =>
			expect(document.body.textContent).toContain('Backend connected · 0 datasets')
		);
	});

	it('collapses the nav into a hamburger overlay below the tablet breakpoint', async () => {
		await page.viewport(390, 844);
		render(Layout, { children });
		// Phone-sized viewport: the desktop nav is hidden and the menu button shows.
		const open = page.getByRole('button', { name: 'Open menu' });
		await expect.element(open).toBeVisible();
		await open.click();
		const menu = page.getByRole('dialog');
		await expect.element(menu).toBeVisible();
		await expect.element(menu.getByRole('navigation', { name: 'Mobile' })).toBeInTheDocument();
		expect(menu.getByRole('link').elements()).toHaveLength(8);
		await page.getByRole('button', { name: 'Close' }).click();
		await vi.waitFor(() => expect(page.getByRole('dialog').elements()).toHaveLength(0));
	});

	it('offers the theme in the mobile menu as a labelled row, and it switches the theme there', async () => {
		await page.viewport(390, 844);
		localStorage.setItem(THEME_STORAGE_KEY, 'dark');
		render(Layout, { children });
		// The header pill is desktop-only.
		expect(
			page
				.getByRole('radiogroup', { name: 'Theme' })
				.elements()
				.filter((el) => el.checkVisibility())
		).toHaveLength(0);
		await page.getByRole('button', { name: 'Open menu' }).click();
		const menu = page.getByRole('dialog');
		await expect.element(menu).toBeVisible();
		const row = menu.getByTestId('menu-theme');
		await expect.element(row).toHaveTextContent('Theme');
		const light = menu.getByRole('radio', { name: 'Light' });
		await expect.element(light).toBeVisible();
		// Labelled segments with touch-sized targets.
		expect(light.element().textContent?.trim()).toBe('Light');
		expect(light.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
		await light.click();
		expect(document.documentElement.getAttribute('data-theme')).toBe('light');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
		// The menu itself repaints (the sheet eases its colours over 200 ms, so poll).
		await expect
			.poll(() => getComputedStyle(menu.element()).backgroundColor)
			.toBe('rgb(250, 250, 250)');
		// Arrow keys work inside the dialog too.
		light.element().focus();
		await userEvent.keyboard('{ArrowLeft}');
		expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
		// The theme row adds radios to the menu, not links.
		expect(row.getByRole('link').elements()).toHaveLength(0);
		expect(row.getByRole('radio').elements()).toHaveLength(3);
	});
});
