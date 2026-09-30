import { createRawSnippet } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
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
			.element(nav.getByRole('link', { name: 'Datasets' }))
			.not.toHaveAttribute('aria-current');
		await expect.element(page.getByRole('button', { name: 'Import CSV' })).toBeInTheDocument();
		await expect.element(page.getByText('page content')).toBeInTheDocument();
	});

	it('is dark-only: no theme toggle, canvas background', async () => {
		render(Layout, { children });
		expect(page.getByRole('button', { name: /theme/i }).elements()).toHaveLength(0);
		expect(getComputedStyle(document.body).backgroundColor).toBe('rgb(9, 9, 9)');
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
		expect(menu.getByRole('link').elements()).toHaveLength(6);
		await page.getByRole('button', { name: 'Close' }).click();
		await vi.waitFor(() => expect(page.getByRole('dialog').elements()).toHaveLength(0));
	});
});
