/**
 * Load policy for a list page whose first paint comes from SSR — /bestof and
 * /activity (the web image shadow-copies a +page.server.ts in; the default
 * build has none, so there those pages get no `data` at all).
 *
 * The rule is one comparison: **fetch unless what is on screen was rendered for
 * the visitor looking at it.** Which covers:
 *
 * - **Anonymous, anonymous batch** — no fetch. SSR queried the API anonymously,
 *   which is exactly what this visitor's own request would return, so refetching
 *   only flashes a spinner over content that is already correct. This case was
 *   not merely wasteful, it was a bug: crawlers are always anonymous, robots.txt
 *   disallows /api/, so Google's renderer refused the fetch, the page's catch
 *   replaced the server-rendered grid with "Error loading photos", and Search
 *   Console classified /bestof as a **soft 404** (HTTP 200 on a
 *   not-found-shaped page). Leaving SSR content alone is what makes these pages
 *   indexable at all.
 * - **No batch at all** (Tauri, `bun run dev`) — load, or the page stays an
 *   empty shell.
 * - **Signed in, anonymous batch** — load: it lacks their hidden-content
 *   filtering. This was every signed-in visit before the server had a ticket.
 * - **Signed in, their own batch** — no fetch. The whole point of the ticket.
 * - **Signed in, somebody else's batch** — load. Rare but real: a document
 *   restored from back/forward cache after signing in as another account.
 *
 * Returns a plain function to drive from a reactive statement:
 *
 *     const syncLoad = createSsrBackedLoad(data ? data.viewer_id : false, () => void loadPhotos());
 *     $: syncLoad($auth);
 *
 * Auth resolves asynchronously, hence the `checked` gate (set by the layout's
 * checkAuth on every route): is_authenticated reads false for a signed-in
 * visitor until then, and acting on it would fetch the anonymous view. Driving
 * it from the store means a later login or logout reloads too — a logout makes
 * the wanted viewer null, which no longer matches the signed-in batch on screen.
 */
export interface VisitorAuth {
	/** Auth hydration has settled — the id below is now meaningful. */
	checked: boolean;
	is_authenticated: boolean;
	/** The signed-in visitor's user id, or null/undefined when anonymous. */
	userId?: string | null;
}

/**
 * Whose view is on screen: a user id, null for the anonymous view, or NO_BATCH
 * when there is nothing rendered yet.
 *
 * The server can now render a signed-in batch (it forwards the visitor's SSR
 * ticket — see $lib/ssrAuth.server), so "did this come from SSR" no longer
 * answers the question; "who is it for" does. One comparison covers every case
 * the old four-state machine spelled out, plus one it could not see: a document
 * restored from back/forward cache after the visitor signed in as someone else.
 */
const NO_BATCH = Symbol('no-batch');
type ShowingFor = string | null | typeof NO_BATCH;

/** The id an SSR batch was rendered for. `viewer_id` comes from the API itself,
 *  so an expired or revoked ticket reads as anonymous rather than claiming to be
 *  the visitor's own — see viewerIdOf. */
export type SsrBatchViewer = string | null | undefined;

export function createSsrBackedLoad(
	ssrBatchViewer: SsrBatchViewer | false,
	load: () => unknown
): (visitor: VisitorAuth) => void {
	// `false` and `undefined` both mean "no server batch at all" (Tauri, dev
	// server), which must always load or the page stays an empty shell.
	let showingFor: ShowingFor =
		ssrBatchViewer === false || ssrBatchViewer === undefined ? NO_BATCH : ssrBatchViewer;

	return (visitor: VisitorAuth) => {
		if (!visitor.checked) return;
		const wanted = visitor.is_authenticated ? (visitor.userId ?? null) : null;
		if (showingFor === wanted) return;
		showingFor = wanted;
		load();
	};
}
