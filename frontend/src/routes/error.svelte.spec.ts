import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page as browserPage } from 'vitest/browser';
import ErrorPage from './+error.svelte';

// SvelteKit hands the error page its status and message through `$app/state`. The component keeps
// the first `page` object it imports, so tests mutate that object instead of replacing it.
const state = vi.hoisted(() => ({ page: { status: 404, error: { message: 'Not Found' } } }));
vi.mock('$app/state', () => state);

describe('error page', () => {
	it('explains a missing page and offers a way back, instead of rendering blank', async () => {
		Object.assign(state.page, { status: 404, error: { message: 'Not found: /docz' } });
		render(ErrorPage);
		await expect
			.element(browserPage.getByRole('heading', { level: 1, name: 'Page not found' }))
			.toBeInTheDocument();
		await expect.element(browserPage.getByText('Error 404')).toBeInTheDocument();
		await expect
			.element(browserPage.getByRole('link', { name: 'Datasets' }))
			.toHaveAttribute('href', '/');
		await expect
			.element(browserPage.getByRole('link', { name: 'Docs' }))
			.toHaveAttribute('href', '/docs');
	});

	it('shows the message for other failures', async () => {
		Object.assign(state.page, { status: 500, error: { message: 'Failed to load module' } });
		render(ErrorPage);
		await expect
			.element(browserPage.getByRole('heading', { level: 1, name: 'Something went wrong' }))
			.toBeInTheDocument();
		await expect.element(browserPage.getByText('Failed to load module')).toBeInTheDocument();
	});
});
