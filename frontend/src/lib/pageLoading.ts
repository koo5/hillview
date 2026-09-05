/**
 * "This page is not showing you your own view yet."
 *
 * The web build server-renders a handful of routes, and the server has no
 * session (tokens live in IndexedDB), so those pages paint an ANONYMOUS view
 * first and correct it on the client once auth has settled — see
 * `createSsrBackedLoad` for the policy and why the anonymous batch is kept for
 * anonymous visitors. Between those two paints the page looks finished but is
 * telling a signed-in visitor something that is not true of them: no hidden
 * content filtering, `user_rating` null, no own-photo affordances.
 *
 * Pages report their viewer-correcting load through `trackLoad`. The layout
 * turns the count into one `data-loading` attribute on <html>, which drives the
 * "Loading…" indicator and gives tests something honest to wait for. Together
 * with `data-hydrated` (set once the layout has mounted) the two attributes say:
 *
 *   html[data-hydrated]:not([data-loading])   — wired, and showing YOUR view
 *
 * Only wrap discrete, terminating fetches. A long-lived stream (the map's photo
 * sources) must stay out of this, or the page would never read as ready; those
 * have their own per-source spinners.
 */
import { writable } from 'svelte/store';

/** Number of viewer-correcting loads in flight. */
export const pendingLoads = writable(0);

/** Run `work`, counting it as in flight for as long as it takes. */
export async function trackLoad<T>(work: () => Promise<T>): Promise<T> {
	pendingLoads.update((n) => n + 1);
	try {
		return await work();
	} finally {
		pendingLoads.update((n) => Math.max(0, n - 1));
	}
}
