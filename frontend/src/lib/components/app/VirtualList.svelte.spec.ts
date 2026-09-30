import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import Harness from '$lib/testing/VirtualListHarness.svelte';

const rows = () => document.querySelectorAll('[data-testid="virtual-row"]');

describe('VirtualList', () => {
	it('renders only the visible window for a very large list', async () => {
		render(Harness, { count: 100_000 });
		await expect.element(page.getByText('Row 0', { exact: true })).toBeInTheDocument();
		// 300px viewport / 30px rows = 10 visible, plus overscan on one side at the top.
		expect(rows().length).toBeLessThan(40);
		expect(rows().length).toBeGreaterThan(5);
		const table = page.getByRole('table', { name: 'Test rows' }).element();
		expect(table.getAttribute('aria-rowcount')).toBe('100001');
	});

	it('moves the window when scrolled and keeps the row count bounded', async () => {
		render(Harness, { count: 100_000 });
		const scroller = page.getByRole('table', { name: 'Test rows' }).element() as HTMLElement;
		scroller.scrollTop = 30 * 50_000;
		scroller.dispatchEvent(new Event('scroll'));
		await expect.element(page.getByText('Row 50000', { exact: true })).toBeInTheDocument();
		expect(document.body.textContent).not.toContain('Row 0 ');
		expect(rows().length).toBeLessThan(40);
	});

	it('shows the empty snippet instead of rows', async () => {
		render(Harness, { count: 0 });
		await expect.element(page.getByText('Nothing here')).toBeInTheDocument();
		expect(rows().length).toBe(0);
	});
});
