/**
 * Client key registration — the session-level owner of "does the server know
 * this device's ECDSA public key under the signed-in user?".
 *
 * The server needs the key wherever it verifies something this device signed:
 * upload authorization (409 `client_key_not_registered` when the key is
 * unknown), the upload finalize signature check, the stream credential (a 401
 * that an EventSource client cannot read the reason of), and push-token
 * ownership on Android. Those consumers multiply and do not all surface a
 * missing key in a way the client can act on, so registration is not left to
 * whichever request happens to need the key first. It starts at login, retries in the background, and every
 * consumer that needs the key awaits `ensureClientKeyRegistered()` instead of
 * relying on the order in which auth state flipped.
 *
 * Login itself never fails over this. Under host load the token POST has been
 * seen to succeed in 259 ms while register-client-key hung for tens of seconds,
 * and the user was told to check their credentials
 * (docs/todo/load-resilience.md).
 *
 * Retry policy: network failures and 5xx retry on a doubling delay, about a
 * minute in total, then the run gives up and waits to be kicked — by the next
 * consumer calling `ensureClientKeyRegistered()`, or by connectivity returning.
 * A 4xx other than 409 (already registered) means the request itself is wrong
 * and is not retried; a session ending stops the run.
 *
 * The 409 self-heal in `requestUploadAuthorization` (uploadProtocol.ts) is the
 * backstop for state this module cannot see: a server-side DB reset, a server
 * URL switch, and the service worker, which has no access to this module.
 */

import { createTokenManager } from './tokenManagerFactory';
import { ClientKeyRegistrationError } from './tokenManager';
import { onReconnect } from './connectivity';

const LOG_PREFIX = '🢄[ClientKey]';

/** Delay before each retry; the run gives up once these are spent. */
export const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 16000, 32000];

// Someone in this session wanted the key registered (login, or a consumer).
let sessionWantsKey = false;
// The server confirmed the key in this session.
let registered = false;
// The run in progress, shared by every concurrent caller.
let run: Promise<void> | null = null;
// Bumped by reset so a run that outlives its session cannot write state.
let generation = 0;

/**
 * Kick off registration for a freshly established session. Fire-and-forget:
 * the outcome is logged here and surfaced to whichever consumer needs the key.
 */
export function startClientKeyRegistration(): void {
	registered = false;
	ensureClientKeyRegistered().catch(() => {
		// Logged inside the run. The next consumer or reconnect re-kicks it.
	});
}

/**
 * Resolves once the server knows this device's key for the current session.
 * Starts a run if none is in flight; rejects when the run gives up, when the
 * server rejects the key outright, or when the session ends meanwhile.
 */
export function ensureClientKeyRegistered(): Promise<void> {
	sessionWantsKey = true;
	if (registered) return Promise.resolve();
	if (!run) run = performRun();
	return run;
}

/** Forget everything about the previous session. Called from logout. */
export function resetClientKeyRegistration(): void {
	sessionWantsKey = false;
	registered = false;
	run = null;
	generation++;
}

/** Test seam: the state a fresh page load would have. */
export function _resetForTests(): void {
	resetClientKeyRegistration();
}

async function performRun(): Promise<void> {
	const gen = generation;
	try {
		for (let attempt = 0; ; attempt++) {
			try {
				await registerOnce();
				assertSameSession(gen);
				registered = true;
				console.log(`${LOG_PREFIX} Client key registered`);
				return;
			} catch (error) {
				assertSameSession(gen);
				const message = error instanceof Error ? error.message : String(error);
				if (!isRetryable(error)) {
					console.error(`${LOG_PREFIX} Client key registration rejected, not retrying: ${message}`);
					throw error;
				}
				if (attempt >= RETRY_DELAYS_MS.length) {
					console.error(`${LOG_PREFIX} Client key registration gave up after ${attempt + 1} attempts: ${message}`);
					throw error;
				}
				const delay = RETRY_DELAYS_MS[attempt];
				console.warn(`${LOG_PREFIX} Client key registration failed (${message}); retrying in ${delay} ms (attempt ${attempt + 1}/${RETRY_DELAYS_MS.length + 1})`);
				await new Promise(resolve => setTimeout(resolve, delay));
				assertSameSession(gen);
			}
		}
	} finally {
		if (gen === generation) run = null;
	}
}

async function registerOnce(): Promise<void> {
	const tokenManager = createTokenManager();
	// Android: Kotlin registers the key itself when it stores tokens, and heals
	// at upload time; the JS side has nothing to do.
	if (!('registerClientPublicKey' in tokenManager)) return;
	await (tokenManager as { registerClientPublicKey(): Promise<void> }).registerClientPublicKey();
}

function isRetryable(error: unknown): boolean {
	// The session ended under us; the next login starts its own run.
	if (error instanceof Error && error.name === 'TokenExpiredError') return false;
	// The server answered: only its own failures are worth another try.
	if (error instanceof ClientKeyRegistrationError) return error.status >= 500;
	// No answer at all (network, timeout, http.ts status-0 wrapper).
	return true;
}

function assertSameSession(gen: number): void {
	if (gen !== generation) {
		throw new SessionChangedError();
	}
}

class SessionChangedError extends Error {
	constructor() {
		super('Session changed during client key registration');
		this.name = 'SessionChangedError';
	}
}

// A run that gave up is re-kicked when the network or the tab comes back,
// but only for a session that asked for the key and still lacks it.
onReconnect(() => {
	if (sessionWantsKey && !registered && !run) {
		ensureClientKeyRegistered().catch(() => {});
	}
});
