/**
 * Mirrors the SSR read ticket into a cookie so the frontend's own server can
 * render this visitor's view.
 *
 * Why a cookie at all, when tokens live in IndexedDB: the server sees only what
 * the browser sends with the document request, and IndexedDB is not that. In
 * production the API answers on api.hillview.cz while the site is hillview.cz,
 * so the backend cannot set this cookie either — it has to be written here, on
 * the frontend's own origin.
 *
 * What is in it is deliberately not the access token: the ticket is minted with
 * type "ssr_read" and every write path rejects it (see SSR_READ_TOKEN_TYPE in
 * backend auth.py), so a stolen cookie cannot act on the user's behalf. It
 * cannot be HttpOnly, since JS writes it — parity with IndexedDB, which is
 * equally script-readable.
 *
 * Not available off the main thread. The service worker refreshes tokens on its
 * own and has no `document`; it announces the change over the `hillview-auth`
 * BroadcastChannel instead, and webTokenManager's subscriber calls back in here.
 */

import { TAURI } from '$lib/tauri';
import { SSR_TICKET_COOKIE } from './ssrTicketCookieName';

const COOKIE_NAME = SSR_TICKET_COOKIE;

/**
 * Whether a ticket cookie means anything here.
 *
 * Two places where the answer is no, and neither is a failure:
 * - no `document` — nothing that runs off the main thread imports this, but
 *   the guard costs nothing and keeps a stray server import from throwing;
 * - Tauri — the app build has no server rendering at all, and its origin has no
 *   cookie jar any server would read.
 */
function cookiesApply(): boolean {
	return typeof document !== 'undefined' && !TAURI;
}

/**
 * Matches our cookie carrying an actual value.
 *
 * By name, not by prefix — `xhv_ssr=` is a different cookie. And the value must
 * be non-empty: a name with nothing after it is not a ticket, and treating it as
 * one made the clear path report failure on engines that blank a cookie instead
 * of dropping it (happy-dom does; browsers vary).
 */
const COOKIE_PRESENT = new RegExp(`(?:^|;\\s*)${COOKIE_NAME}=[^;\\s]`);

let warned = false;

/**
 * Write, then check it took.
 *
 * A refusal is survivable — the server renders anonymously, as it did before any
 * of this existed — but it is not something to swallow in silence, because the
 * only symptom is a signed-in visitor quietly getting the anonymous first paint.
 * Two ways it can happen, both worth one line in the console:
 *
 * - the assignment throws, which a sandboxed frame with no storage access does;
 * - the assignment is ignored, which a browser with cookies blocked does, and
 *   which no try/catch can see. Hence the read-back.
 *
 * Warned once per page: a browser that refuses the first write refuses every
 * one, and this runs on every token refresh.
 */
function write(cookie: string, expectPresent: boolean): void {
	try {
		document.cookie = cookie;
	} catch (err) {
		if (!warned) {
			warned = true;
			console.warn('🍪 SSR ticket cookie refused; pages will render the anonymous view', err);
		}
		return;
	}

	if (COOKIE_PRESENT.test(document.cookie) !== expectPresent && !warned) {
		warned = true;
		console.warn(
			expectPresent
				? '🍪 SSR ticket cookie did not stick (cookies blocked?); pages will render the anonymous view'
				: '🍪 SSR ticket cookie could not be cleared'
		);
	}
}

/**
 * Write (or overwrite) the ticket cookie.
 *
 * `expiresAt` is the ticket's own expiry, so the cookie dies with it rather than
 * lingering as a credential the server would reject anyway. A ticket without a
 * usable expiry is treated as no ticket: better to render anonymously than to
 * pin a cookie whose lifetime nobody knows.
 */
export function setSsrTicketCookie(ticket: string | undefined, expiresAt: string | undefined): void {
	if (!cookiesApply()) return;
	if (!ticket) {
		clearSsrTicketCookie();
		return;
	}

	const expiry = expiresAt ? Date.parse(expiresAt) : NaN;
	const maxAge = Number.isFinite(expiry) ? Math.floor((expiry - Date.now()) / 1000) : NaN;
	if (!Number.isFinite(maxAge) || maxAge <= 0) {
		clearSsrTicketCookie();
		return;
	}

	// Lax rather than Strict: the server has to receive this on a top-level
	// navigation from anywhere (a shared link, a search result), which is exactly
	// the case Lax allows and Strict does not. Secure everywhere the origin is
	// https; on a plain-http dev origin the attribute would make the cookie
	// unwritable, so it is set only when the page itself is secure.
	const attrs = [
		`${COOKIE_NAME}=${encodeURIComponent(ticket)}`,
		'Path=/',
		'SameSite=Lax',
		`Max-Age=${maxAge}`
	];
	if (location.protocol === 'https:') attrs.push('Secure');

	write(attrs.join('; '), true);
}

/** Drop the cookie — logout, and any path that clears stored tokens. */
export function clearSsrTicketCookie(): void {
	if (!cookiesApply()) return;
	const attrs = [`${COOKIE_NAME}=`, 'Path=/', 'SameSite=Lax', 'Max-Age=0'];
	if (location.protocol === 'https:') attrs.push('Secure');
	write(attrs.join('; '), false);
}

/** The name the server reads — lives in ssrTicketCookieName.ts, re-exported for callers here. */
export { SSR_TICKET_COOKIE };
