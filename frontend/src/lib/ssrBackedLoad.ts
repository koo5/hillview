/**
 * Load policy for a list page whose first paint comes from SSR — /bestof and
 * /activity (the web image shadow-copies a +page.server.ts in; the default
 * build has none, so there those pages get no `data` at all).
 *
 * Three visitors, three needs:
 *
 * - **Anonymous with an SSR batch** — no fetch at all. SSR queries the API
 *   anonymously, which is exactly what this visitor's own request would
 *   return, so refetching only flashes a spinner over content that is already
 *   correct. This case was not merely wasteful, it was a bug: crawlers are
 *   always anonymous, robots.txt disallows /api/, so Google's renderer refused
 *   the fetch, the page's catch replaced the server-rendered grid with "Error
 *   loading photos", and Search Console classified /bestof as a **soft 404**
 *   (HTTP 200 on a not-found-shaped page). Leaving SSR content alone is what
 *   makes these pages indexable at all.
 * - **Anonymous without an SSR batch** (Tauri, `bun run dev`) — load, or the
 *   page stays an empty shell.
 * - **Signed in** — load, always: SSR cannot see their session (tokens live in
 *   IndexedDB), so the SSR batch lacks their hidden-content filtering.
 *
 * Returns a plain function to drive from a reactive statement:
 *
 *     const syncLoad = createSsrBackedLoad(!!data?.photos, () => void loadPhotos());
 *     $: syncLoad($auth);
 *
 * Auth resolves asynchronously, hence the `checked` gate (set by the layout's
 * checkAuth on every route): is_authenticated reads false for a signed-in
 * visitor until then, and acting on it would fetch the anonymous view. Driving
 * it from the store means a later login or logout reloads too.
 */
export interface VisitorAuth {
	/** Auth hydration has settled — is_authenticated is now meaningful. */
	checked: boolean;
	is_authenticated: boolean;
}

/** Whose view the displayed list currently is. 'ssr' is the anonymous server
 *  batch: already right for an anonymous visitor, not for a signed-in one. */
type LoadedFor = 'nothing' | 'ssr' | 'anon' | 'auth';

export function createSsrBackedLoad(
	hasSsrData: boolean,
	load: () => unknown
): (visitor: VisitorAuth) => void {
	let loadedFor: LoadedFor = hasSsrData ? 'ssr' : 'nothing';

	return (visitor: VisitorAuth) => {
		if (!visitor.checked) return;
		if (visitor.is_authenticated) {
			if (loadedFor === 'auth') return;
			loadedFor = 'auth';
		} else {
			if (loadedFor === 'anon' || loadedFor === 'ssr') return;
			loadedFor = 'anon';
		}
		load();
	};
}
