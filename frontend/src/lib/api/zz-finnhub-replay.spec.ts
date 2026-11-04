import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parseCatalog, parseProviders, parseQueryResponse } from './providers';

const dir = '/tmp/finnhub_responses';
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}`, 'utf8'));

describe('finnhub replay (temporary)', () => {
	it('catalog and providers parse', () => {
		expect(parseCatalog(read('_catalog.json')).endpoints.length).toBe(113);
		expect(parseProviders(read('_providers.json'))[0].id).toBe('finnhub');
	});
	for (const file of readdirSync(dir).filter((f) => !f.startsWith('_'))) {
		it(file, () => {
			expect(() => parseQueryResponse(read(file))).not.toThrow();
		});
	}
});
