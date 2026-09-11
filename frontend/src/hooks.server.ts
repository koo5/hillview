import { sequence } from "@sveltejs/kit/hooks";
import { handleErrorWithSentry, sentryHandle } from "@sentry/sveltekit";
import type { Handle } from "@sveltejs/kit";
import { env } from "$env/dynamic/private";
import { SSR_TICKET_COOKIE } from "$lib/ssrTicketCookieName";

/**
 * Authed server rendering.
 *
 * The web build server-renders a handful of routes for crawlers, but tokens live
 * in the browser's IndexedDB, so without this the server has no credential and
 * every render is the anonymous view — which the client then has to correct. The
 * browser mirrors a read-only ticket into a cookie (see $lib/ssrTicketCookie);
 * this reads it into locals, and the four server loads forward it to the API.
 *
 * Runtime switch, not a build-time one: `VITE_` variables bake at build time, so
 * SSR_AUTH lives in the container's environment and a restart is enough to turn
 * this off. Off means the loads fall back to anonymous rendering with the client
 * correcting it. The Vary header below stays on either way: it costs nothing,
 * and a cache that holds copies from both sides of a flip must not mix them.
 */
const ssrAuthEnabled = () => (env.SSR_AUTH ?? 'on').toLowerCase() !== 'off';

const ssrAuth: Handle = async ({ event, resolve }) => {
	const ticket = ssrAuthEnabled() ? event.cookies.get(SSR_TICKET_COOKIE) : undefined;
	event.locals.ssrTicket = ticket || undefined;

	const response = await resolve(event);

	// Which responses can carry a per-visitor view: the document, and the
	// __data.json a client-side navigation fetches for it.
	//
	// `event.isDataRequest` rather than a look at the path — SvelteKit strips the
	// data-request marker from `event.url` before hooks run, so matching on
	// "/__data.json" would never fire for a real one, and *would* fire for a route
	// whose own parameter happened to spell it (/user_by_name/…/__data.json).
	const isDocument = (response.headers.get('content-type') ?? '').includes('text/html');
	if (!isDocument && !event.isDataRequest) return response;

	// Vary regardless of whether a ticket was used: without it a cache holding the
	// anonymous copy could serve it to a signed-in visitor, or the reverse. Append,
	// because Caddy's `encode` adds its own Vary: Accept-Encoding.
	const vary = response.headers.get('vary');
	if (!/(^|,)\s*cookie\s*(,|$)/i.test(vary ?? '')) {
		response.headers.set('vary', vary ? `${vary}, Cookie` : 'Cookie');
	}

	if (event.locals.ssrTicket) {
		// private bars shared caches; no-cache forces revalidation while leaving
		// back/forward cache working, which no-store would have killed. The tradeoff
		// is that this HTML may sit in the browser's own disk cache — acceptable for
		// photo listings and ratings, which are not credentials.
		response.headers.set('cache-control', 'private, no-cache');
	}

	return response;
};

// Custom handlers go after sentryHandle() in the sequence.
export const handle = sequence(sentryHandle(), ssrAuth);

// If you have a custom error handler, pass it to `handleErrorWithSentry`
export const handleError = handleErrorWithSentry();
