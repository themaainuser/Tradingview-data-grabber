import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page, userEvent } from 'vitest/browser';
import { API_ENDPOINTS } from '$lib/docs/api-reference';
import { OPERATORS } from '$lib/filters/operators';
import { INDICATORS } from '$lib/indicators';
import { METRICS } from '$lib/research/columns';
import DocsInLayout from '$lib/testing/DocsInLayout.svelte';
import Docs from './+page.svelte';

// The app shell reads the current route from SvelteKit.
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/docs') } }));

const count = (selector: string) => document.querySelectorAll(selector).length;

afterEach(() => {
	vi.restoreAllMocks();
	document.body.innerHTML = '';
});

describe('Docs page', () => {
	it('renders every section with a matching contents link', async () => {
		await page.viewport(1440, 900);
		render(Docs);
		await expect.element(page.getByRole('heading', { level: 1, name: 'Docs' })).toBeInTheDocument();
		const links = [...document.querySelectorAll('nav[aria-label="Documentation contents"] a')];
		expect(links).toHaveLength(12);
		for (const link of links) {
			const id = link.getAttribute('href')!.slice(1);
			const section = document.getElementById(id);
			expect(section, id).not.toBeNull();
			expect(section!.tagName).toBe('SECTION');
			// Each section is named by its own heading, for screen readers.
			expect(section!.getAttribute('aria-labelledby')).toBe(`${id}-title`);
			expect(document.getElementById(`${id}-title`)).not.toBeNull();
		}
	});

	it('lists the contents in the order the sections appear, so the scroll-spy follows the page', async () => {
		render(Docs);
		await expect.element(page.getByRole('heading', { level: 1, name: 'Docs' })).toBeInTheDocument();
		const listed = [...document.querySelectorAll('nav[aria-label="Documentation contents"] a')].map(
			(a) => a.getAttribute('href')!.slice(1)
		);
		const onPage = [...document.querySelectorAll('section[id]')].map((s) => s.id);
		expect(listed).toEqual(onPage);
	});

	it('generates the reference from the code, so it cannot drift', async () => {
		render(Docs);
		await expect.element(page.getByTestId('indicator-reference')).toBeInTheDocument();
		expect(count('[data-testid=operator-row]')).toBe(OPERATORS.length);
		expect(count('[data-testid=indicator-item]')).toBe(INDICATORS.length);
		expect(count('[data-testid=endpoint]')).toBe(API_ENDPOINTS.length);
		expect(count('[data-testid=metric-row]')).toBe(METRICS.length);
		// Look-ahead operators carry their warning wherever they are documented.
		const warned = [...document.querySelectorAll('[data-testid=operator-row]')].filter((r) =>
			r.textContent?.includes('Uses the whole sample')
		);
		expect(warned).toHaveLength(OPERATORS.filter((o) => o.lookahead).length);
	});

	it('searches and filters the indicator reference', async () => {
		render(Docs);
		const total = INDICATORS.length;
		await expect
			.element(page.getByTestId('indicator-count'))
			.toHaveTextContent(`Showing ${total} of ${total}`);

		await page.getByRole('searchbox', { name: 'Search indicators' }).fill('relative strength');
		const matching = INDICATORS.filter((d) =>
			`${d.name} ${d.short} ${d.id} ${d.description}`.toLowerCase().includes('relative strength')
		).length;
		await expect
			.element(page.getByTestId('indicator-count'))
			.toHaveTextContent(`Showing ${matching} of ${total}`);
		expect(count('[data-testid=indicator-item]')).toBe(matching);

		await page.getByRole('searchbox', { name: 'Search indicators' }).fill('zzzz nothing');
		await expect
			.element(page.getByText('No indicator matches “zzzz nothing”.'))
			.toBeInTheDocument();
		expect(count('[data-testid=indicator-item]')).toBe(0);

		await page.getByRole('searchbox', { name: 'Search indicators' }).fill('');
		await page.getByRole('radio', { name: 'Volume' }).click();
		const volume = INDICATORS.filter((d) => d.category === 'Volume').length;
		await expect
			.element(page.getByTestId('indicator-count'))
			.toHaveTextContent(`Showing ${volume} of ${total}`);
		// Choosing the active category again returns to "All" instead of leaving nothing selected.
		await page.getByRole('radio', { name: 'Volume' }).click();
		await expect
			.element(page.getByTestId('indicator-count'))
			.toHaveTextContent(`Showing ${total} of ${total}`);
	});

	it('copies a command exactly as written and announces it', async () => {
		const writeText = vi.fn(async () => {});
		Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
		render(Docs);
		const first = page.getByRole('button', { name: 'Copy to clipboard' }).nth(1);
		await first.click();
		expect(writeText).toHaveBeenCalledWith('tvdata serve --data-dir data');
		await vi.waitFor(() => expect(document.body.textContent).toContain('Copied'));
	});

	it('shows a visible failure state when the clipboard is unavailable', async () => {
		const writeText = vi.fn(async () => {
			throw new Error('denied');
		});
		Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
		render(Docs);
		await page.getByRole('button', { name: 'Copy to clipboard' }).first().click();
		const failed = page.getByRole('button', { name: 'Copy failed, select the text instead' });
		await expect.element(failed).toBeInTheDocument();
		// A coral alert icon is shown, so the failure is not conveyed by the label alone.
		const icon = failed.element().querySelector('svg.text-coral-ink') as SVGElement;
		expect(icon.getAttribute('class')).toContain('opacity-100');
		await expect
			.element(page.getByText('Copy failed. Select the text and copy it manually.'))
			.toBeInTheDocument();
	});

	it('expands a troubleshooting answer on demand', async () => {
		render(Docs);
		const trigger = page.getByRole('button', { name: 'The dashboard is empty' });
		const answer = page.getByText(/That is expected until data exists/);
		await expect.element(trigger).toHaveAttribute('aria-expanded', 'false');
		// Closed content stays in the DOM but hidden, so it is not announced or shown.
		await expect.element(answer).not.toBeVisible();
		await trigger.click();
		await expect.element(trigger).toHaveAttribute('aria-expanded', 'true');
		await expect.element(answer).toBeVisible();
		await trigger.click();
		await expect.element(answer).not.toBeVisible();
	});

	it('keeps keyboard access to scrollable code blocks', async () => {
		render(Docs);
		await userEvent.tab();
		const pre = document.querySelector('figure pre') as HTMLElement;
		expect(pre.getAttribute('tabindex')).toBe('0');
	});

	it('fits a phone-width screen without sideways page scroll', async () => {
		// Regression: implicit grid columns sized to the widest table or command line and pushed the
		// whole page past the viewport. Wide content must scroll inside its own container instead.
		// Mounted in the real app shell so its padding and the contents bar's negative margins match.
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => new Response(JSON.stringify({ datasets: [] })))
		);
		await page.viewport(390, 844);
		render(DocsInLayout);
		await expect.element(page.getByRole('heading', { level: 1, name: 'Docs' })).toBeInTheDocument();
		const root = document.documentElement;
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
		const code = document.querySelector('figure pre') as HTMLElement;
		expect(code.getBoundingClientRect().right).toBeLessThanOrEqual(root.clientWidth);
		vi.unstubAllGlobals();
	});

	it('never shows market data: documentation only', async () => {
		render(Docs);
		await expect.element(page.getByRole('heading', { level: 1, name: 'Docs' })).toBeInTheDocument();
		expect(count('canvas')).toBe(0);
		expect(document.body.textContent).toContain('There is no sample data.');
	});
});
