import { vi } from 'vitest';

export const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

type Handler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

/**
 * Replaces `fetch` with a router over path prefixes (longest match wins). A request no route
 * claims fails the test loudly instead of reaching whatever listens behind Vite's proxy.
 */
export function stubBackend(routes: Record<string, Handler>) {
	const calls: string[] = [];
	const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input), 'http://localhost');
		calls.push(url.pathname + url.search);
		const key = Object.keys(routes)
			.filter((prefix) => url.pathname.startsWith(prefix))
			.sort((a, b) => b.length - a.length)[0];
		if (!key) throw new Error(`unstubbed request: ${url.pathname}${url.search}`);
		return routes[key](url, init);
	});
	vi.stubGlobal('fetch', fetch);
	return { calls, fetch };
}
