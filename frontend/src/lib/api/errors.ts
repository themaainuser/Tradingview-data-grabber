export type ApiErrorKind =
	/** The request never produced a response (offline, refused, DNS, CORS). */
	| 'network'
	| 'timeout'
	| 'aborted'
	/** The backend answered with a non-2xx status. */
	| 'http'
	/** The backend answered 2xx but the payload broke the documented contract. */
	| 'contract';

export class ApiError extends Error {
	readonly kind: ApiErrorKind;
	readonly status: number | null;

	constructor(kind: ApiErrorKind, message: string, status: number | null = null, cause?: unknown) {
		super(message, { cause });
		this.name = 'ApiError';
		this.kind = kind;
		this.status = status;
	}

	/** Worth offering a "Retry" button: transient transport/server faults, not user mistakes. */
	get retryable(): boolean {
		return (
			this.kind === 'network' ||
			this.kind === 'timeout' ||
			(this.kind === 'http' && (this.status ?? 0) >= 500)
		);
	}
}

export function isAbort(error: unknown): boolean {
	return error instanceof ApiError
		? error.kind === 'aborted'
		: error instanceof DOMException && error.name === 'AbortError';
}

/** Turns anything thrown into an ApiError so UI code handles exactly one error type. */
export function toApiError(error: unknown): ApiError {
	if (error instanceof ApiError) return error;
	const message = error instanceof Error ? error.message : String(error);
	return new ApiError('network', message, null, error);
}
