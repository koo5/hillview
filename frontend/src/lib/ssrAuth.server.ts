/**
 * Server-load helpers for rendering the visitor's own view.
 *
 * The ticket arrives from hooks.server.ts (read from a cookie the browser
 * mirrors it into) and goes to the API as an ordinary bearer token. The API
 * accepts it on exactly the read endpoints SSR calls; anything that writes
 * rejects it, so the worst a leaked ticket buys is a read the visitor could do
 * anyway. See SSR_READ_TOKEN_TYPE in backend auth.py.
 */

/**
 * Who a server-rendered batch was filtered for: a user id, or null for the
 * anonymous view.
 *
 * Deliberately an id and not a boolean, and deliberately taken from the API's
 * own `viewer_id` rather than from the ticket we sent. Those two choices cover
 * the cases a boolean cannot:
 *
 * - the ticket was expired or its session revoked, so the API answered
 *   anonymously — the batch is anonymous and says so, instead of claiming to be
 *   the visitor's;
 * - the document was restored from back/forward cache after the visitor signed
 *   in as somebody else — the id no longer matches, so the page refetches
 *   instead of showing the previous account's view.
 */
export type SsrViewerId = string | null;

/** Bearer header for the visitor's ticket, or no headers when anonymous. */
export function ssrAuthHeaders(locals: App.Locals): Record<string, string> {
	return locals.ssrTicket ? { Authorization: `Bearer ${locals.ssrTicket}` } : {};
}

/**
 * Read `viewer_id` off an API response body.
 *
 * Anything unexpected reads as anonymous, which is the safe direction: the page
 * then refetches under its own token rather than trusting a batch whose owner it
 * cannot establish.
 */
export function viewerIdOf(body: unknown): SsrViewerId {
	if (!body || typeof body !== 'object') return null;
	const id = (body as { viewer_id?: unknown }).viewer_id;
	return typeof id === 'string' && id ? id : null;
}
