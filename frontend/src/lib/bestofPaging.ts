/**
 * ?page= handling for the /bestof ranking.
 *
 * Only the parsing lives here. The slice size and the step between slices are
 * the same number and belong together, so they stay in the API
 * (BESTOF_PAGE_SIZE in bestof_routes.py) — the frontend passes a page number
 * and never derives an offset. Splitting that arithmetic across two codebases
 * is how the two halves drift apart, and the failure is silent: a step under
 * the size repeats photos across pages, a step over it leaves photos that no
 * page lists at all, unreachable by any crawler.
 *
 * In $lib rather than in +page.server.ts.web because SvelteKit permits only
 * load/prerender/csr/ssr/… as exports there, and the shadow file is swapped in
 * at Docker build time, so vitest never sees it.
 */

/** Read ?page=, tolerating junk: absent, 0, -3, "abc" and 1.5 all mean page 1. */
export function parsePageParam(raw: string | null): number {
	const n = Number(raw);
	return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1;
}
