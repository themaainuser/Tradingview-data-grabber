import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import { goto } from '$app/navigation';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import { page as routePage } from '$lib/testing/route.svelte';
import fixtures from '$lib/testing/trading-fixtures.json';
import Trading from './[[env]]/[[view]]/+page.svelte';

vi.mock('$app/state', () => import('$lib/testing/route.svelte'));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

type Json = Record<string, unknown>;
const answer = (name: keyof typeof fixtures, over: Json = {}): Json => ({
	...(fixtures[name] as unknown as Json),
	...over
});

/** The environments as the backend lists them; `live` turns the live one on. */
const environments = (live: boolean) => ({
	...fixtures.environments,
	environments: fixtures.environments.environments.map((e) =>
		e.id === 'live' ? { ...e, enabled: live, configured: live, note: live ? null : e.note } : e
	)
});

function backend(
	options: {
		live?: boolean;
		routes?: Record<string, (url: URL, init?: RequestInit) => Response>;
	} = {}
) {
	const b = stubBackend({
		'/api/datasets': () => json({ datasets: [] }),
		'/api/trading/environments': () => json(environments(options.live ?? false)),
		'/api/trading/paper/account': () => json(answer('account')),
		'/api/trading/paper/clock': () => json(answer('clock')),
		'/api/trading/paper/positions': () => json(answer('positions')),
		'/api/trading/paper/orders': (_, init) =>
			init?.method === 'POST' ? json(answer('order_filled')) : json(answer('orders')),
		'/api/trading/paper/quote': () => json(answer('quote_stock')),
		'/api/trading/paper/assets': () => json(answer('assets')),
		...Object.fromEntries(
			['paper', 'live'].flatMap((env) => [
				[
					`/api/trading/${env}/account/configurations`,
					() => json(answer('config', { environment: env }))
				],
				[
					`/api/trading/${env}/account/portfolio-history`,
					() => json(answer('history', { environment: env }))
				],
				[
					`/api/trading/${env}/account/activities`,
					() => json(answer('activities', { environment: env }))
				],
				[
					`/api/trading/${env}/watchlists`,
					(url: URL) =>
						json(
							url.pathname.endsWith('/watchlists')
								? answer('watchlists', { environment: env })
								: answer('watchlist', { environment: env })
						)
				]
			])
		),
		'/api/trading/live/account': () => json(answer('account', { environment: 'live' })),
		'/api/trading/live/clock': () => json(answer('clock', { environment: 'live' })),
		'/api/trading/live/positions': () => json(answer('positions', { environment: 'live' })),
		'/api/trading/live/orders': () => json(answer('orders', { environment: 'live' })),
		'/api/trading/live/quote': () => json(answer('quote_stock', { environment: 'live' })),
		...options.routes
	});
	return b;
}

const posted = (b: ReturnType<typeof backend>) =>
	b.fetch.mock.calls.filter(
		([, init]) => init?.method === 'POST' || init?.method === 'DELETE' || init?.method === 'PATCH'
	);

beforeEach(() => {
	routePage.params = { env: 'paper', view: undefined };
});
afterEach(() => {
	vi.unstubAllGlobals();
	vi.mocked(goto).mockClear();
	document.body.innerHTML = '';
});

const mount = async () => {
	await page.viewport(1280, 900);
	render(InApp, { page: Trading });
};

describe('Trading page: which account you are on', () => {
	it('says paper trading in green, shows the account, and has not sent anything that changes', async () => {
		const b = backend();
		await mount();
		const banner = page.getByTestId('environment-banner');
		await expect.element(banner).toHaveTextContent('Paper trading · simulated money');
		await expect.element(banner).toHaveAttribute('data-real-money', 'false');
		await expect.element(page.getByTestId('stat-equity')).toHaveTextContent('$100,000.00');
		await expect.element(page.getByTestId('account-number')).toHaveTextContent('PA3TESTACCT');
		expect(posted(b)).toHaveLength(0);
	});

	it('opens paper when the address names no environment, never live', async () => {
		routePage.params = { env: undefined, view: undefined };
		backend({ live: true });
		await mount();
		await expect.poll(() => vi.mocked(goto).mock.calls.length).toBeGreaterThan(0);
		expect(String(vi.mocked(goto).mock.calls[0][0])).toContain('/trading/paper');
	});

	it('says live in red when it is on, and shows the real-money warning', async () => {
		routePage.params = { env: 'live', view: undefined };
		backend({ live: true });
		await mount();
		const banner = page.getByTestId('environment-banner');
		await expect.element(banner).toHaveTextContent('LIVE trading · real money');
		await expect.element(banner).toHaveAttribute('data-real-money', 'true');
	});

	it('shows how to turn live on, and requests nothing from live, while it is off', async () => {
		routePage.params = { env: 'live', view: undefined };
		const b = backend({ live: false });
		await mount();
		await expect
			.element(page.getByTestId('trading-setup'))
			.toHaveTextContent('ALPACA_ENABLE_LIVE_TRADING=true');
		await expect
			.element(page.getByRole('navigation', { name: 'Trading sections' }))
			.not.toBeInTheDocument();
		expect(b.calls.filter((c) => c.startsWith('/api/trading/live'))).toEqual([]);
	});

	it('says an unknown environment is not found instead of showing an account', async () => {
		routePage.params = { env: 'demo', view: undefined };
		backend();
		await mount();
		await expect.element(page.getByText('Environment not found')).toBeVisible();
	});
});

describe('Trading page: the order ticket', () => {
	beforeEach(() => {
		routePage.params = { env: 'paper', view: 'trade' };
	});

	it('says what is wrong beside the fields and sends nothing', async () => {
		const b = backend();
		await mount();
		await page.getByTestId('review-order').click();
		await expect.element(page.getByText('Enter a symbol such as AAPL')).toBeVisible();
		await expect.element(page.getByText('The quantity is required.')).toBeVisible();
		await expect.element(page.getByTestId('order-review')).not.toBeInTheDocument();
		expect(posted(b)).toHaveLength(0);
	});

	it('reviews first, then sends exactly the order that was reviewed, once', async () => {
		const b = backend();
		await mount();
		await page.getByLabelText('Symbol').fill('aapl');
		await page.getByLabelText('Quantity').fill('10');
		await page.getByTestId('review-order').click();
		await expect
			.element(page.getByTestId('review-text'))
			.toHaveTextContent('Buy 10 AAPL at market · Day');
		await expect.element(page.getByTestId('place-order')).toHaveTextContent('Place paper order');
		expect(posted(b)).toHaveLength(0); // reviewing sends nothing

		await page.getByTestId('place-order').click();
		await expect
			.element(page.getByTestId('notice'))
			.toHaveTextContent('Order placed: buy AAPL (filled)');
		const sent = posted(b);
		expect(sent).toHaveLength(1);
		expect(JSON.parse(String(sent[0][1]?.body))).toMatchObject({
			symbol: 'AAPL',
			side: 'buy',
			type: 'market',
			time_in_force: 'day',
			qty: '10',
			client_order_id: expect.stringMatching(/^tvdata-/)
		});
		expect(new Headers(sent[0][1]?.headers).get('X-Tvdata-Trading')).toBe('1');
		await expect.element(page.getByTestId('order-review')).not.toBeInTheDocument();
	});

	it('offers only what the kind of asset offers, and asks for the exit prices of a bracket', async () => {
		backend();
		await mount();
		await page.getByLabelText('Symbol').fill('BTC/USD');
		await expect.element(page.getByTestId('asset-kind')).toHaveTextContent('Crypto');
		await page.getByLabelText('Order type').click();
		const types = await page.getByRole('option').elements();
		expect(types.map((o) => o.textContent?.trim())).toEqual(['Market', 'Limit', 'Stop limit']);
		await page.getByRole('option', { name: 'Market' }).click();
		await page.getByLabelText('Symbol').fill('AAPL');
		await page.getByLabelText('Order class').click();
		await page.getByRole('option', { name: /Bracket/ }).click();
		await expect.element(page.getByTestId('exit-legs')).toBeVisible();
	});

	it('shows Alpaca’s reason when it refuses, and keeps the order for editing', async () => {
		const b = backend({
			routes: {
				'/api/trading/paper/orders': (_, init) =>
					init?.method === 'POST' ? json(answer('order_refused')) : json(answer('orders'))
			}
		});
		await mount();
		await page.getByLabelText('Symbol').fill('AAPL');
		await page.getByLabelText('Quantity').fill('100000');
		await page.getByTestId('review-order').click();
		await page.getByTestId('place-order').click();
		await expect
			.element(page.getByTestId('order-outcome'))
			.toHaveTextContent('insufficient buying power');
		await expect.element(page.getByLabelText('Quantity')).toHaveValue('100000');
		expect(posted(b)).toHaveLength(1);
	});

	it('puts the net price and the legs in a multi-leg order and starts it as a limit order', async () => {
		backend();
		await mount();
		await page.getByRole('radio', { name: 'Multi-leg option' }).click();
		await expect.element(page.getByTestId('legs')).toBeVisible();
		await expect.element(page.getByLabelText('Net price')).toBeVisible();
		await page.getByTestId('review-order').click();
		await expect.element(page.getByText('two to four legs')).toBeVisible();
	});
});

describe('Trading page: live asks for the word LIVE', () => {
	beforeEach(() => {
		routePage.params = { env: 'live', view: 'trade' };
	});

	it('keeps the place button off until LIVE is typed exactly, then sends to the live route', async () => {
		const b = backend({
			live: true,
			routes: {
				'/api/trading/live/orders': (_, init) =>
					init?.method === 'POST'
						? json(answer('order_filled', { environment: 'live' }))
						: json(answer('orders', { environment: 'live' }))
			}
		});
		await mount();
		await page.getByLabelText('Symbol').fill('AAPL');
		await page.getByLabelText('Quantity').fill('1');
		await page.getByTestId('review-order').click();
		const place = page.getByTestId('place-order');
		await expect.element(place).toHaveTextContent('Place LIVE order');
		await expect.element(place).toBeDisabled();
		await page.getByTestId('live-confirm').fill('live');
		await expect.element(place).toBeDisabled();
		await page.getByTestId('live-confirm').fill('LIVE');
		await expect.element(place).toBeEnabled();
		expect(posted(b)).toHaveLength(0);
		await place.click();
		await expect.poll(() => posted(b).length).toBe(1);
		expect(String(posted(b)[0][0])).toContain('/api/trading/live/orders');
	});
});

describe('Trading page: positions', () => {
	beforeEach(() => {
		routePage.params = { env: 'paper', view: 'positions' };
	});

	it('lists what is held and keeps the close box open with its message when the quantity is too large', async () => {
		const b = backend();
		await mount();
		const row = page.getByTestId('position-row');
		await expect.element(row).toHaveTextContent('AAPL');
		await row.getByRole('button', { name: 'Close…' }).click();
		await page.getByRole('radio', { name: 'Quantity' }).click();
		await page.getByLabelText('Quantity to close').fill('99');
		await page.getByRole('button', { name: 'Close it' }).click();
		await expect.element(page.getByText('You hold 10.')).toBeVisible();
		await expect.element(page.getByTestId('confirm-box')).toBeVisible();
		expect(posted(b)).toHaveLength(0);
	});

	it('sends the close once the quantity is valid', async () => {
		const b = backend({
			routes: {
				'/api/trading/paper/positions': (_, init) =>
					init?.method === 'DELETE' ? json(answer('order_filled')) : json(answer('positions'))
			}
		});
		await mount();
		await page.getByTestId('position-row').getByRole('button', { name: 'Close…' }).click();
		await page.getByRole('button', { name: 'Close it' }).click();
		await expect.poll(() => posted(b).length).toBe(1);
		expect(posted(b)[0][1]?.method).toBe('DELETE');
		expect(String(posted(b)[0][0])).toContain('/api/trading/paper/positions/AAPL');
	});
});

describe('Trading page: orders', () => {
	beforeEach(() => {
		routePage.params = { env: 'paper', view: 'orders' };
	});

	it('draws the orders with their exit legs nested and offers cancel only on open ones', async () => {
		backend();
		await mount();
		await expect.element(page.getByTestId('orders-table')).toBeVisible();
		const rows = await page.getByTestId('order-row').elements();
		expect(rows.length).toBeGreaterThan(4);
		const statuses = rows.map((r) => r.getAttribute('data-status'));
		expect(statuses).toContain('held');
		const cancelable = rows.filter((r) => r.textContent?.includes('Cancel'));
		expect(
			cancelable.every((r) =>
				['accepted', 'new', 'partially_filled'].includes(r.getAttribute('data-status') ?? '')
			)
		).toBe(true);
	});
});

describe('Trading page: switching account', () => {
	const calls = (b: ReturnType<typeof backend>, path: string) =>
		b.calls.filter((c) => c.startsWith(path));

	it.each([
		['settings', '/account/configurations'],
		['activity', '/account/activities'],
		['watchlists', '/watchlists'],
		['overview', '/account/portfolio-history']
	])(
		'reads what the %s view shows again for the account that was switched to',
		async (view, path) => {
			routePage.params = { env: 'paper', view };
			const b = backend({ live: true });
			await mount();
			await expect.poll(() => calls(b, `/api/trading/paper${path}`).length).toBeGreaterThan(0);
			expect(calls(b, `/api/trading/live${path}`)).toEqual([]);
			routePage.params = { env: 'live', view };
			await expect.poll(() => calls(b, `/api/trading/live${path}`).length).toBeGreaterThan(0);
			await expect
				.element(page.getByTestId('environment-banner'))
				.toHaveAttribute('data-real-money', 'true');
		}
	);

	it('drops an open review and the draft, so an order reviewed on paper cannot be sent to live', async () => {
		routePage.params = { env: 'paper', view: 'trade' };
		const b = backend({ live: true });
		await mount();
		await page.getByLabelText('Symbol').fill('AAPL');
		await page.getByLabelText('Quantity').fill('10');
		await page.getByTestId('review-order').click();
		await expect.element(page.getByTestId('order-review')).toBeVisible();

		routePage.params = { env: 'live', view: 'trade' };
		await expect
			.element(page.getByTestId('environment-banner'))
			.toHaveAttribute('data-real-money', 'true');
		await expect.element(page.getByTestId('order-review')).not.toBeInTheDocument();
		await expect.element(page.getByTestId('place-order')).not.toBeInTheDocument();
		await expect.element(page.getByLabelText('Symbol')).toHaveValue('');
		await expect.element(page.getByLabelText('Quantity')).toHaveValue('');
		expect(posted(b)).toHaveLength(0);
	});
});

describe('Trading page: live asks for LIVE before it changes or deletes anything', () => {
	const open = (view: string, env = 'live') => {
		routePage.params = { env, view };
		return backend({ live: true });
	};

	it('cancelling one live order needs the word, and cancelling on paper does not', async () => {
		const b = open('orders');
		await mount();
		const row = page.getByTestId('order-row').filter({ hasText: 'Accepted' }).first();
		await row.getByRole('button', { name: 'Cancel', exact: true }).click();
		const confirm = page.getByRole('button', { name: 'Cancel the order' });
		await expect.element(page.getByTestId('live-confirm')).toBeVisible();
		await expect.element(confirm).toBeDisabled();
		expect(posted(b)).toHaveLength(0);
		await page.getByTestId('live-confirm').fill('LIVE');
		await expect.element(confirm).toBeEnabled();
	});

	it('cancelling one paper order is a single click', async () => {
		const b = open('orders', 'paper');
		await mount();
		await page
			.getByTestId('order-row')
			.filter({ hasText: 'Accepted' })
			.first()
			.getByRole('button', { name: 'Cancel', exact: true })
			.click();
		await expect.poll(() => posted(b).length).toBe(1);
		expect(posted(b)[0][1]?.method).toBe('DELETE');
		await expect.element(page.getByTestId('live-confirm')).not.toBeInTheDocument();
	});

	it('replacing a live order keeps the button off until LIVE is typed, and paper has no such field', async () => {
		const b = open('orders');
		await mount();
		await page
			.getByTestId('order-row')
			.filter({ hasText: 'TSLA' })
			.getByRole('button', { name: 'Replace', exact: true })
			.click();
		await page.getByLabelText('Limit price').fill('310');
		const send = page.getByRole('button', { name: 'Replace order' });
		await expect.element(page.getByTestId('replace-live-confirm')).toBeVisible();
		await expect.element(send).toBeDisabled();
		await page.getByTestId('replace-live-confirm').fill('live');
		await expect.element(send).toBeDisabled();
		await page.getByTestId('replace-live-confirm').fill('LIVE');
		await expect.element(send).toBeEnabled();
		expect(posted(b)).toHaveLength(0);
	});

	it('replacing a paper order asks for no word', async () => {
		open('orders', 'paper');
		await mount();
		await page
			.getByTestId('order-row')
			.filter({ hasText: 'TSLA' })
			.getByRole('button', { name: 'Replace', exact: true })
			.click();
		await expect.element(page.getByRole('button', { name: 'Replace order' })).toBeEnabled();
		await expect.element(page.getByTestId('replace-live-confirm')).not.toBeInTheDocument();
	});

	it('deleting a live watchlist needs the word, and deleting a paper one does not', async () => {
		const b = open('watchlists');
		await mount();
		await expect.element(page.getByTestId('watchlist-detail')).toBeVisible();
		await page.getByRole('button', { name: 'Delete', exact: true }).click();
		await expect.element(page.getByTestId('live-confirm')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Delete the watchlist' })).toBeDisabled();
		expect(posted(b)).toHaveLength(0);

		document.body.innerHTML = '';
		open('watchlists', 'paper');
		await mount();
		await expect.element(page.getByTestId('watchlist-detail')).toBeVisible();
		await page.getByRole('button', { name: 'Delete', exact: true }).click();
		await expect.element(page.getByRole('button', { name: 'Delete the watchlist' })).toBeEnabled();
		await expect.element(page.getByTestId('live-confirm')).not.toBeInTheDocument();
	});
});
