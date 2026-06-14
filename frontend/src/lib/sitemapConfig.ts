// URLs per child sitemap page. Kept well under the protocol's 50,000-URL /
// 50MB-per-file limit. Shared by the sitemap index (computes page count) and
// the photo page route (slice size) — they MUST agree.
export const SITEMAP_PAGE_SIZE = 40000;
