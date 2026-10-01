import type { QueryStatus } from '$lib/api/providers';

export interface StatusCopy {
	title: string;
	/** What it means and what to do, in one or two sentences. */
	advice: string;
	/** `premium` gets the premium accent; `error` the error treatment; the rest are plain notices. */
	tone: 'premium' | 'error' | 'notice';
}

/** Words for every query outcome that is not data. Nothing is ever drawn instead of data. */
export function statusCopy(status: Exclude<QueryStatus, 'ok'>, keyEnv: string): StatusCopy {
	switch (status) {
		case 'premium_required':
			return {
				title: 'Premium access required',
				advice:
					'This key is not entitled to this endpoint or option. The provider answers with sample data in this case; it is not shown here, because it is not real data.',
				tone: 'premium'
			};
		case 'rate_limited':
			return {
				title: 'Request limit reached',
				advice:
					'The provider is limiting requests for this key. Wait and try again later; repeated identical requests are served from the cache and do not count.',
				tone: 'notice'
			};
		case 'not_configured':
			return {
				title: 'No API key configured',
				advice: `Add ${keyEnv} to the backend's environment or .env file and restart it. The key is read by the backend only and is never sent to the browser.`,
				tone: 'notice'
			};
		case 'invalid_key':
			return {
				title: 'The API key was not accepted',
				advice: `The provider rejected the key in ${keyEnv}. Check that it is correct and has not been revoked, then restart the backend.`,
				tone: 'error'
			};
		case 'invalid_request':
			return {
				title: 'The provider rejected this request',
				advice: 'Check the parameters against the endpoint documentation and try again.',
				tone: 'error'
			};
		case 'upstream_error':
			return {
				title: 'The provider could not be reached',
				advice:
					'This is a problem on the provider side or on the network. Nothing was cached; try again shortly.',
				tone: 'error'
			};
		case 'empty':
			return {
				title: 'No data returned',
				advice:
					'The provider answered without any data for these parameters. Try a different symbol, date or interval.',
				tone: 'notice'
			};
	}
}
