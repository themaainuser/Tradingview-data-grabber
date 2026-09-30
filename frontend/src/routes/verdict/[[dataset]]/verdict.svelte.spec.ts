import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { page } from 'vitest/browser';
import type { VerdictReport, VerdictState } from '$lib/api/contracts';
import InApp from '$lib/testing/InApp.svelte';
import { json, stubBackend } from '$lib/testing/backend';
import {
	captureRules,
	freeze,
	holdout,
	holdoutResult,
	passedRule,
	report,
	rule,
	verdictState
} from '$lib/testing/verdict-fixtures';
import Verdict from './+page.svelte';

const route = vi.hoisted(() => ({
	page: {
		url: new URL('http://localhost/verdict/abc'),
		params: { dataset: 'abc' as string | undefined }
	}
}));
vi.mock('$app/state', () => route);
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

const summary = {
	id: 'abc',
	symbol: 'BINANCE:BTCUSDT',
	timeframe: '60',
	path: 'BINANCE_BTCUSDT/60.csv',
	rows: 1000,
	size_bytes: 1,
	modified: '2026-09-29T12:00:28Z',
	start: 1,
	end: 2,
	valid: true,
	error: null
};

interface Call {
	method: string;
	path: string;
	body: unknown;
}

/** A stateful stand-in for the backend: it stores what it is sent, the way the real one does. */
function fakeBackend(initial: VerdictState, nextReport: () => VerdictReport) {
	let state = initial;
	const calls: Call[] = [];
	const handler = (url: URL, init?: RequestInit) => {
		const method = init?.method ?? 'GET';
		const body = init?.body ? JSON.parse(String(init.body)) : null;
		calls.push({ method, path: url.pathname, body });
		const path = url.pathname;
		if (method === 'GET' && path === '/api/verdict/abc') return json(state);
		if (method === 'POST' && path === '/api/verdict/abc/seal') {
			state = { ...state, sealed: true, holdout: holdout({ fraction: body.holdout_fraction }) };
			return json({ holdout: state.holdout });
		}
		if (method === 'POST' && path === '/api/verdict/run') {
			const result = nextReport();
			state = {
				...state,
				sealed: true,
				holdout: state.holdout ?? holdout(),
				ledger: result.ledger,
				latest: result
			};
			return json(result);
		}
		if (method === 'POST' && path === '/api/verdict/abc/freeze') {
			state = { ...state, freeze };
			return json(freeze);
		}
		if (method === 'POST' && path === '/api/verdict/abc/holdout/read') {
			if (state.holdout?.status === 'read') {
				return json(
					{ detail: 'holdout already read on 2026-09-30T00:00:00Z; it cannot be read again' },
					409
				);
			}
			const result = holdoutResult();
			state = {
				...state,
				holdout: holdout({ status: 'read', read_at: result.read_at }),
				holdout_read: result
			};
			return json(result);
		}
		if (method === 'GET' && path === '/api/verdict/abc/forward') {
			return json({
				freeze,
				start: freeze.forward_start,
				end: null,
				bars: 0,
				waiting: true,
				rules: [],
				caveat: 'c',
				sharpe_se_annualised_iid: null
			});
		}
		if (method === 'GET' && path === '/api/verdict/abc/ledger') {
			return json({
				intact: true,
				total_entries: 2,
				trials: { dataset: 16, total: 16, keys: [] },
				entries: [
					{
						seq: 1,
						type: 'seal',
						at: '2026-09-30T00:00:00Z',
						hash: 'aaaaaaaaaaaaaaaa',
						prev: '0',
						summary: 'Sealed the most recent 20% (200 bars)'
					},
					{
						seq: 2,
						type: 'run',
						at: '2026-09-30T00:00:01Z',
						hash: 'bbbbbbbbbbbbbbbb',
						prev: 'a',
						summary: 'Run run-1: INSUFFICIENT_DATA, 16 rules, costs 10/1/0.1'
					}
				]
			});
		}
		return json({ detail: `unhandled ${method} ${path}` }, 500);
	};
	const backend = stubBackend({
		'/api/datasets': () => json({ datasets: [summary] }),
		'/api/verdict': handler
	});
	return {
		calls,
		backend,
		get state() {
			return state;
		}
	};
}

const sealedState = (overrides: Partial<VerdictState> = {}) =>
	verdictState({
		sealed: true,
		holdout: holdout(),
		ledger: { trials_dataset: 16, trials_total: 16, runs_dataset: 1, intact: true },
		...overrides
	});

const candidateReport = () =>
	report(
		'CANDIDATE',
		[
			passedRule('sma-5-20'),
			passedRule('sma-10-20'),
			rule('sma-5-50'),
			rule('rsi-30-50', { status: 'NEVER_TRADES', trades: 0 })
		],
		{
			verdict: {
				label: 'CANDIDATE',
				headline: 'Two rules passed every check.',
				reasons: ['Candidate rules: sma-10-20.']
			}
		}
	);

beforeEach(() => {
	route.page.params.dataset = 'abc';
});
afterEach(() => {
	vi.unstubAllGlobals();
	document.body.innerHTML = '';
});

const mount = async (width = 1440) => {
	await page.viewport(width, 900);
	render(InApp, { page: Verdict });
};
const rows = () => [...document.querySelectorAll<HTMLElement>('[data-testid="rule-row"]')];

describe('Verdict page: before any run', () => {
	it('shows the setup, says nothing has been run, and draws no verdict or statistics', async () => {
		fakeBackend(verdictState(), () => report());
		await mount();
		await expect
			.element(page.getByRole('button', { name: 'Seal holdout and run verdict' }))
			.toBeEnabled();
		await expect
			.element(page.getByTestId('no-verdict'))
			.toHaveTextContent('Nothing has been run on this dataset');
		expect(document.querySelector('[data-testid="verdict-banner"]')).toBeNull();
		expect(document.querySelector('[data-testid="rule-row"]')).toBeNull();
		expect(document.querySelector('[data-testid="holdout-section"]')).toBeNull();
		await expect.element(page.getByLabelText('Minimum trades per rule')).toHaveValue(30);
		await expect.element(page.getByLabelText('Fee (bps per side)')).toHaveValue(10);
	});

	it('shows the backend\u2019s cost basis so the assumptions can be checked', async () => {
		fakeBackend(verdictState(), () => report());
		await mount();
		await expect.element(page.getByText(/Binance spot taker, regular tier/)).toBeInTheDocument();
		await expect
			.element(page.getByText(/Placeholder: captures contain no bid\/ask data/))
			.toBeInTheDocument();
	});
});

describe('Verdict page: the real-capture case', () => {
	it('seals, runs, and reports INSUFFICIENT_DATA with nothing tested or ranked', async () => {
		const { calls } = fakeBackend(verdictState(), () =>
			report('INSUFFICIENT_DATA', captureRules())
		);
		await mount();
		await page.getByRole('radio', { name: '25%' }).click();
		await page.getByRole('button', { name: 'Seal holdout and run verdict' }).click();

		await expect.element(page.getByTestId('verdict-label')).toHaveTextContent('Insufficient data');
		expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual([
			'/api/verdict/abc/seal',
			'/api/verdict/run'
		]);
		expect(calls.find((c) => c.path.endsWith('/seal'))?.body).toEqual({ holdout_fraction: 0.25 });
		expect(calls.find((c) => c.path === '/api/verdict/run')?.body).toEqual({
			dataset_id: 'abc',
			min_trades: 30,
			costs: { fee_bps_per_side: 10, spread_bps: 1, slippage_k: 0.1 },
			periods_per_year: null
		});

		expect(rows()).toHaveLength(16);
		expect(rows().every((r) => r.querySelector('[data-testid="not-tested"]'))).toBe(true);
		// Not tested means no statistic anywhere in the row, not even a dash-filled column.
		for (const row of rows()) expect(row.textContent).not.toMatch(/\u00b1/);
		expect(rows().filter((r) => r.dataset.status === 'NEVER_TRADES')).toHaveLength(3);
		await expect.element(page.getByTestId('no-statistics')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="effective-n"]')).toBeNull();
		await expect.element(page.getByTestId('ledger-n')).toHaveTextContent('16');
	});

	it('keeps the holdout locked and offers no way to freeze or read it', async () => {
		fakeBackend(sealedState({ latest: report('INSUFFICIENT_DATA', captureRules()) }), () =>
			report()
		);
		await mount();
		await expect.element(page.getByTestId('holdout-locked')).toHaveTextContent('No rule qualified');
		expect(document.querySelector('[data-testid="finalists"]')).toBeNull();
		expect(document.querySelector('[data-testid="read-holdout"]')).toBeNull();
		expect(page.getByRole('button', { name: /Read the holdout/ }).elements()).toHaveLength(0);
		expect(page.getByRole('button', { name: /Freeze/ }).elements()).toHaveLength(0);
	});

	it('orders rows only by grid or by trade count, never by performance', async () => {
		fakeBackend(sealedState({ latest: report('INSUFFICIENT_DATA', captureRules()) }), () =>
			report()
		);
		await mount();
		await expect.element(page.getByTestId('rules-section')).toBeInTheDocument();
		const grid = rows().map((r) => r.querySelector('th')?.textContent?.trim().split('\n')[0]);
		expect(grid[0]).toContain('SMA 5/20');
		expect(
			page.getByRole('group', { name: 'Row order' }).getByRole('radio').elements()
		).toHaveLength(2);

		await page.getByRole('radio', { name: 'Most trades' }).click();
		const trades = rows().map((r) => Number(r.querySelectorAll('td')[1].textContent?.trim()));
		expect(trades).toEqual([...trades].sort((a, b) => b - a));
		// No row or heading in the rules table names a winner.
		expect(document.querySelector('[data-testid="rules-section"]')?.textContent).not.toMatch(
			/\b(best|top|winning|winner)\b/i
		);
	});

	it('explains the verdict, the meaning of the label and the reasons', async () => {
		fakeBackend(sealedState({ latest: report('INSUFFICIENT_DATA', captureRules()) }), () =>
			report()
		);
		await mount();
		await expect
			.element(page.getByTestId('verdict-headline'))
			.toHaveTextContent('Nothing can be concluded or ranked');
		await expect.element(page.getByTestId('uncertainty')).toHaveTextContent('\u00b13.3');
		await expect
			.element(page.getByTestId('integrity-section'))
			.toHaveTextContent('Next bar\u2019s open');
	});
});

describe('Verdict page: a candidate, freeze and the single holdout read', () => {
	it('shows evidence for rules that qualified, with the checks as text', async () => {
		fakeBackend(sealedState({ latest: candidateReport() }), () => report());
		await mount();
		await expect.element(page.getByTestId('verdict-label')).toHaveTextContent('Candidate');
		const first = rows()[0];
		expect(first.dataset.candidate).toBe('true');
		expect(first.textContent).toContain('1.10 \u00b1 2.9');
		expect(first.textContent).toContain('0.012');
		expect(first.textContent).toContain('0.970');
		expect(first.textContent).toMatch(/Bootstrap\s*passed/);
		expect(rows()[2].querySelector('[data-testid="not-tested"]')).not.toBeNull();
		await expect
			.element(page.getByTestId('effective-n'))
			.toHaveTextContent('90% bootstrap interval 2.1 to 6.4');
		// The claim reads "p = 0.012", and backend prose names rules the way the table does.
		await expect.element(page.getByTestId('reality-check')).toHaveTextContent('p = 0.012');
		await expect
			.element(page.getByTestId('verdict-banner'))
			.toHaveTextContent('Candidate rules: SMA 10/20.');
		expect(document.querySelector('[data-testid="verdict-banner"]')?.textContent).not.toContain(
			'sma-10-20'
		);
		await expect
			.element(page.getByTestId('pbo-noisy'))
			.toHaveTextContent('Noisy at this sample length');
	});

	it('writes a vanishing p-value as "p < 0.001", never "p = <0.001" or zero', async () => {
		const tiny = candidateReport();
		tiny.statistics!.reality_check.p_value = 0;
		fakeBackend(sealedState({ latest: tiny }), () => report());
		await mount();
		await expect.element(page.getByTestId('reality-check')).toHaveTextContent('p < 0.001');
		expect(document.querySelector('[data-testid="reality-check"]')?.textContent).not.toContain(
			'= <'
		);
	});

	it('walks freeze then a confirmed one-time read, then shows the result with its caveat', async () => {
		const fake = fakeBackend(sealedState({ latest: candidateReport() }), () => report());
		await mount();

		// Only candidates can be frozen, at most two, and freezing needs a selection.
		await expect
			.element(page.getByRole('button', { name: 'Freeze selected rules' }))
			.toBeDisabled();
		expect(page.getByRole('checkbox', { name: 'SMA 5/50' }).elements()).toHaveLength(0);
		await page.getByRole('checkbox', { name: 'SMA 5/20' }).click();
		await page.getByRole('checkbox', { name: 'SMA 10/20' }).click();
		await page.getByRole('button', { name: 'Freeze selected rules' }).click();
		await expect.element(page.getByTestId('frozen')).toHaveTextContent('SMA 5/20');
		expect(fake.calls.find((c) => c.path.endsWith('/freeze'))?.body).toEqual({
			run_id: 'run-1',
			rule_ids: ['sma-5-20', 'sma-10-20']
		});

		// The read is gated behind an explicit acknowledgement.
		const read = page.getByRole('button', { name: 'Read the holdout once' });
		await expect.element(read).toBeDisabled();
		await page.getByRole('checkbox', { name: /I understand/ }).click();
		await expect.element(read).toBeEnabled();
		await read.click();

		await expect.element(page.getByTestId('holdout-result')).toBeInTheDocument();
		await expect
			.element(page.getByTestId('holdout-caveat'))
			.toHaveTextContent('This is a sanity check, not a verdict.');
		await expect
			.element(page.getByTestId('holdout-status'))
			.toHaveTextContent('cannot be read again');
		expect(document.querySelector('[data-testid="read-holdout"]')).toBeNull();
		expect(page.getByRole('button', { name: 'Read the holdout once' }).elements()).toHaveLength(0);
		expect(fake.calls.filter((c) => c.path.endsWith('/holdout/read'))).toHaveLength(1);
	});

	it('shows the backend\u2019s refusal when a second read is attempted elsewhere', async () => {
		// Another tab already read it: this tab still thinks it is unread, then the backend says no.
		const fake = fakeBackend(sealedState({ latest: candidateReport(), freeze }), () => report());
		await mount();
		await expect.element(page.getByTestId('read-holdout')).toBeInTheDocument();
		const { state: served } = fake;
		void served;
		// Flip the server to "already read" without telling the page.
		await fetch('/api/verdict/abc/holdout/read', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ freeze_id: 'f1' })
		});
		await page.getByRole('checkbox', { name: /I understand/ }).click();
		await page.getByRole('button', { name: 'Read the holdout once' }).click();
		await expect.element(page.getByTestId('read-error')).toHaveTextContent('cannot be read again');
		// The page re-syncs and stops offering the read.
		await vi.waitFor(() =>
			expect(document.querySelector('[data-testid="read-holdout"]')).toBeNull()
		);
		await expect.element(page.getByTestId('holdout-result')).toBeInTheDocument();
	});

	it('reports that no bars have arrived since the freeze, instead of a result', async () => {
		fakeBackend(sealedState({ latest: candidateReport(), freeze }), () => report());
		await mount();
		await page.getByRole('button', { name: 'Check new bars' }).click();
		await expect
			.element(page.getByTestId('forward-waiting'))
			.toHaveTextContent('No bars have been captured since the freeze');
	});
});

describe('Verdict page: other verdicts, validation and failure', () => {
	it('locks the holdout when the verdict is indistinguishable from luck', async () => {
		const notCandidate = passedRule('sma-5-20', {
			candidate: false,
			adjusted_p: 0.41,
			checks: { bootstrap: false, dsr: true, stress: true }
		});
		fakeBackend(
			sealedState({ latest: report('INDISTINGUISHABLE_FROM_LUCK', [notCandidate]) }),
			() => report()
		);
		await mount();
		await expect
			.element(page.getByTestId('verdict-label'))
			.toHaveTextContent('Indistinguishable from luck');
		await expect
			.element(page.getByTestId('holdout-locked'))
			.toHaveTextContent('No rule passed every check');
		expect(rows()[0].textContent).toMatch(/Bootstrap\s*failed/);
	});

	it('blocks the run and explains a bad setting beside the field', async () => {
		const fake = fakeBackend(verdictState(), () => report());
		await mount();
		await page.getByLabelText('Minimum trades per rule').fill('0');
		await expect
			.element(page.getByText('Minimum trades must be between 1 and 1000'))
			.toBeInTheDocument();
		await expect
			.element(page.getByRole('button', { name: 'Seal holdout and run verdict' }))
			.toBeDisabled();
		await page.getByLabelText('Minimum trades per rule').fill('30');
		await page.getByLabelText('Fee (bps per side)').fill('900');
		await expect.element(page.getByText('Fee must be between 0 and 500')).toBeInTheDocument();
		expect(fake.calls.filter((c) => c.method === 'POST')).toHaveLength(0);
	});

	it('treats an empty periods-per-year field as "infer it", not an error', async () => {
		fakeBackend(verdictState(), () => report());
		await mount();
		await expect
			.element(page.getByRole('button', { name: 'Seal holdout and run verdict' }))
			.toBeEnabled();
		await expect.element(page.getByLabelText('Periods per year')).toHaveValue(null);
		expect(document.body.textContent).not.toContain('Periods per year must be above 0');
	});

	it('notes that the form differs from the verdict on screen', async () => {
		fakeBackend(sealedState({ latest: report('INSUFFICIENT_DATA', captureRules()) }), () =>
			report()
		);
		await mount();
		await expect.element(page.getByTestId('rules-section')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="settings-changed"]')).toBeNull();
		await page.getByLabelText('Fee (bps per side)').fill('25');
		await expect.element(page.getByTestId('settings-changed')).toBeInTheDocument();
	});

	it('disables every action and says why when the ledger chain is broken', async () => {
		fakeBackend(
			sealedState({
				latest: report('INSUFFICIENT_DATA', captureRules()),
				ledger: { trials_dataset: 16, trials_total: 16, runs_dataset: 1, intact: false }
			}),
			() => report()
		);
		await mount();
		await expect
			.element(page.getByTestId('ledger-broken'))
			.toHaveTextContent('hash chain does not verify');
		await expect.element(page.getByRole('button', { name: 'Run verdict' })).toBeDisabled();
		await expect.element(page.getByTestId('ledger-chain')).toHaveTextContent('Broken');
	});

	it('shows the backend\u2019s message when a run is refused', async () => {
		stubBackend({
			'/api/datasets': () => json({ datasets: [summary] }),
			'/api/verdict': (url, init) =>
				init?.method === 'POST'
					? json({ detail: 'the bars before the seal changed since sealing' }, 409)
					: json(sealedState())
		});
		await mount();
		await page.getByRole('button', { name: 'Run verdict' }).click();
		await expect
			.element(page.getByTestId('run-error'))
			.toHaveTextContent('the bars before the seal changed since sealing');
		expect(document.querySelector('[data-testid="verdict-banner"]')).toBeNull();
	});

	it('shows an error panel and nothing else when the state cannot be loaded', async () => {
		stubBackend({
			'/api/datasets': () => json({ datasets: [summary] }),
			'/api/verdict': () => json({ detail: 'dataset not found' }, 404)
		});
		await mount();
		await expect.element(page.getByText('dataset not found')).toBeInTheDocument();
		expect(document.querySelector('[data-testid="verdict-banner"]')).toBeNull();
		expect(page.getByRole('button', { name: /run verdict/i }).elements()).toHaveLength(0);
	});

	it('asks to choose a dataset when none is in the URL, and calls nothing', async () => {
		route.page.params.dataset = undefined;
		const { fetch } = stubBackend({ '/api/datasets': () => json({ datasets: [summary] }) });
		await mount();
		await expect
			.element(page.getByText('Choose a dataset', { exact: true }).first())
			.toBeInTheDocument();
		expect(fetch.mock.calls.some(([u]) => String(u).includes('/api/verdict'))).toBe(false);
	});

	it('explains that verdicts need backend captures when there are none', async () => {
		stubBackend({ '/api/datasets': () => json({ datasets: [] }) });
		await mount();
		await expect.element(page.getByText('No backend datasets to assess')).toBeInTheDocument();
	});

	it('fits a phone-width screen without sideways page scroll', async () => {
		fakeBackend(sealedState({ latest: candidateReport(), freeze }), () => report());
		await mount(390);
		await expect.element(page.getByTestId('verdict-banner')).toBeInTheDocument();
		const root = document.documentElement;
		// On failure, name the element that pushed the page wide instead of just the widths.
		const wide = [...document.body.querySelectorAll<HTMLElement>('*')]
			.filter((el) => {
				if (el.getBoundingClientRect().right <= root.clientWidth + 1) return false;
				for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
					if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(p).overflowX))
						return false;
				}
				return true;
			})
			.slice(0, 4)
			.map((el) => `${el.tagName}.${String(el.className).slice(0, 60)}`);
		expect(wide, 'elements wider than the viewport').toEqual([]);
		expect(root.scrollWidth).toBeLessThanOrEqual(root.clientWidth);
	});
});
