import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS } from './api-reference';
import { observeSections } from './scrollspy';

describe('API reference data', () => {
	it('documents exactly the endpoints the backend serves (mirrors tests/test_api.py)', () => {
		expect(API_ENDPOINTS.map((e) => `${e.method} ${e.path}`).sort()).toEqual(
			[
				'GET /api/datasets',
				'GET /api/datasets/{id}/bars',
				'GET /api/datasets/{id}/charts',
				'GET /api/datasets/{id}/report',
				'GET /api/charts/correlation',
				'GET /api/health',
				'GET /api/providers',
				'GET /api/providers/{provider_id}/catalog',
				'POST /api/providers/{provider_id}/query',
				'GET /api/sentiment/fear-greed',
				'GET /api/verdict/{id}',
				'GET /api/verdict/{id}/forward',
				'GET /api/verdict/{id}/ledger',
				'POST /api/verdict/run',
				'POST /api/verdict/{id}/freeze',
				'POST /api/verdict/{id}/holdout/read',
				'POST /api/verdict/{id}/seal',
				'POST /api/research/run'
			].sort()
		);
	});

	it('has unique ids, a summary, and path parameters that appear in the path', () => {
		expect(new Set(API_ENDPOINTS.map((e) => e.id)).size).toBe(API_ENDPOINTS.length);
		for (const e of API_ENDPOINTS) {
			expect(e.summary.length, e.id).toBeGreaterThan(20);
			for (const p of e.params.filter((p) => p.in === 'path'))
				expect(e.path).toContain(`{${p.name}}`);
			for (const err of e.errors) expect([404, 409, 422, 502]).toContain(err.status);
		}
	});

	it('only claims UI usage for endpoints the client actually calls', () => {
		const used = API_ENDPOINTS.filter((e) => e.usedBy).map((e) => e.path);
		expect(used.sort()).toEqual(
			[
				'/api/charts/correlation',
				'/api/datasets',
				'/api/datasets/{id}/bars',
				'/api/datasets/{id}/charts',
				'/api/providers',
				'/api/providers/{provider_id}/catalog',
				'/api/providers/{provider_id}/query',
				'/api/research/run',
				'/api/sentiment/fear-greed',
				'/api/verdict/run',
				'/api/verdict/{id}',
				'/api/verdict/{id}/forward',
				'/api/verdict/{id}/freeze',
				'/api/verdict/{id}/holdout/read',
				'/api/verdict/{id}/ledger',
				'/api/verdict/{id}/seal'
			].sort()
		);
	});
});

describe('observeSections', () => {
	type Callback = (entries: { target: { id: string }; isIntersecting: boolean }[]) => void;
	let callback: Callback;
	let observed: string[];
	let disconnected: boolean;

	beforeEach(() => {
		observed = [];
		disconnected = false;
		vi.stubGlobal('CSS', { escape: (s: string) => s });
		vi.stubGlobal(
			'IntersectionObserver',
			class {
				constructor(cb: Callback) {
					callback = cb;
				}
				observe(el: { id: string }) {
					observed.push(el.id);
				}
				disconnect() {
					disconnected = true;
				}
			}
		);
	});
	afterEach(() => vi.unstubAllGlobals());

	const root = {
		querySelector: (sel: string) => (sel === '#missing' ? null : { id: sel.slice(1) })
	} as never;
	const enter = (id: string) => callback([{ target: { id }, isIntersecting: true }]);
	const leave = (id: string) => callback([{ target: { id }, isIntersecting: false }]);

	it('observes every section that exists and skips ids with no element', () => {
		observeSections(root, ['a', 'missing', 'b'], () => {});
		expect(observed).toEqual(['a', 'b']);
	});

	it('reports the first section in document order that is in view', () => {
		const seen: string[] = [];
		observeSections(root, ['a', 'b', 'c'], (id) => seen.push(id));
		enter('b');
		enter('c');
		expect(seen.at(-1)).toBe('b');
		enter('a');
		expect(seen.at(-1)).toBe('a');
		leave('a');
		expect(seen.at(-1)).toBe('b');
	});

	it('keeps the previous section active while none is in view', () => {
		const seen: string[] = [];
		observeSections(root, ['a', 'b'], (id) => seen.push(id));
		enter('a');
		leave('a');
		expect(seen).toEqual(['a']);
	});

	it('ignores sections it was not asked about, and disconnects on cleanup', () => {
		const seen: string[] = [];
		const stop = observeSections(root, ['a'], (id) => seen.push(id));
		enter('zzz');
		expect(seen).toEqual([]);
		stop();
		expect(disconnected).toBe(true);
	});

	it('does nothing where IntersectionObserver is unavailable', () => {
		vi.stubGlobal('IntersectionObserver', undefined);
		expect(() => observeSections(root, ['a'], () => {})()).not.toThrow();
	});
});
