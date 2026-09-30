import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import { ApiError } from '$lib/api/errors';
import ErrorPanel from './ErrorPanel.svelte';
import EmptyState from './EmptyState.svelte';

describe('ErrorPanel', () => {
	it('offers retry for transient failures', async () => {
		const onretry = vi.fn();
		render(ErrorPanel, { error: new ApiError('network', 'Cannot reach the backend.'), onretry });
		await expect.element(page.getByRole('alert')).toHaveTextContent('Cannot reach the backend.');
		await page.getByRole('button', { name: 'Retry' }).click();
		expect(onretry).toHaveBeenCalledOnce();
	});

	it('does not offer retry for a request the backend rejected', async () => {
		render(ErrorPanel, {
			error: new ApiError('http', 'Unknown dataset id', 404),
			onretry: () => {}
		});
		await expect.element(page.getByRole('alert')).toHaveTextContent('Unknown dataset id');
		expect(page.getByRole('button', { name: 'Retry' }).elements()).toHaveLength(0);
	});
});

describe('EmptyState', () => {
	it('renders a title and description as a status region', async () => {
		render(EmptyState, { title: 'No datasets yet', description: 'Capture some bars.' });
		await expect.element(page.getByRole('status')).toHaveTextContent('No datasets yet');
		await expect.element(page.getByText('Capture some bars.')).toBeInTheDocument();
	});
});
