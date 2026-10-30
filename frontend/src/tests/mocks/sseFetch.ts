/**
 * A controllable fake of a `fetch` response carrying a text/event-stream body,
 * for tests of StreamSourceLoader (which reads SSE over fetch). The test is the
 * server: it emits events, ends the body, or breaks it. Aborting the request's
 * signal behaves like a real fetch: a pending or later read rejects with an
 * AbortError, and `close` records that the client hung up.
 */
import { vi } from 'vitest';

type ReadResult = { value: Uint8Array; done: false } | { value: undefined; done: true };

function abortError(): Error {
	return Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' });
}

export class MockSseStream {
	/** Called once when the client aborts the request. */
	readonly close = vi.fn();
	private readonly chunks: Uint8Array[] = [];
	private waiting?: { resolve: (r: ReadResult) => void; reject: (e: unknown) => void };
	private ended = false;
	private failure?: unknown;
	private aborted = false;
	private readonly encoder = new TextEncoder();

	constructor(readonly url: string, readonly init?: RequestInit) {
		const signal = init?.signal;
		if (signal) {
			const onAbort = () => {
				if (this.aborted) return;
				this.aborted = true;
				this.close();
				this.settle();
			};
			if (signal.aborted) onAbort();
			else signal.addEventListener('abort', onAbort);
		}
	}

	/** The request's headers, as a plain object with lower-case names. */
	get headers(): Record<string, string> {
		const headers = this.init?.headers;
		if (!headers) return {};
		const pairs: [string, string][] = Array.isArray(headers)
			? (headers as [string, string][])
			: headers instanceof Headers
				? [...headers]
				: Object.entries(headers as Record<string, string>);
		return Object.fromEntries(pairs.map(([name, value]) => [name.toLowerCase(), value]));
	}

	readonly body = {
		getReader: () => ({
			read: () => this.read(),
			cancel: async () => {},
			releaseLock: () => {}
		})
	};

	/** Raw bytes on the wire, for parser-level cases. */
	emitRaw(text: string): void {
		if (this.ended || this.aborted) return;
		this.chunks.push(this.encoder.encode(text));
		this.settle();
	}

	/** One `data:` event carrying `message` as JSON. */
	emit(message: unknown): void {
		this.emitRaw(`data: ${JSON.stringify(message)}\n\n`);
	}

	/** The server ends the body normally. */
	end(): void {
		this.ended = true;
		this.settle();
	}

	/** The connection breaks mid-body. */
	fail(error: unknown = new TypeError('network error')): void {
		this.failure = error;
		this.settle();
	}

	private read(): Promise<ReadResult> {
		return new Promise((resolve, reject) => {
			this.waiting = { resolve, reject };
			this.settle();
		});
	}

	private settle(): void {
		const waiting = this.waiting;
		if (!waiting) return;
		if (this.aborted) {
			this.waiting = undefined;
			waiting.reject(abortError());
		} else if (this.chunks.length > 0) {
			this.waiting = undefined;
			waiting.resolve({ value: this.chunks.shift()!, done: false });
		} else if (this.failure !== undefined) {
			this.waiting = undefined;
			waiting.reject(this.failure);
		} else if (this.ended) {
			this.waiting = undefined;
			waiting.resolve({ value: undefined, done: true });
		}
	}
}

/** A 200 response whose body is `stream`. */
export function sseResponse(stream: MockSseStream): Response {
	return { ok: true, status: 200, body: stream.body, text: async () => '' } as unknown as Response;
}

/** An error response, as the API sends it before any stream starts. */
export function errorResponse(status: number, detail = 'error'): Response {
	return {
		ok: false,
		status,
		body: null,
		text: async () => JSON.stringify({ detail })
	} as unknown as Response;
}
