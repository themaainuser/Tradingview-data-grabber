/**
 * A reactive stand-in for `page` from `$app/state`, for specs that change the address while a page is mounted
 * (`vi.mock('$app/state', () => import('$lib/testing/route.svelte'))`). Assign to `page.params` to navigate.
 */
import { SvelteURL } from 'svelte/reactivity';

export const page = $state({
	url: new SvelteURL('http://localhost/'),
	params: {} as Record<string, string | undefined>
});
