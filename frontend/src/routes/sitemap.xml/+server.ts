import type { RequestHandler } from './$types';
import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
import { backendInternalUrl } from '$lib/config.server';

// Single flat sitemap. robots.txt points crawlers here. Lists the static pages
// plus every curated, public photo as <url> entries directly — no sitemap-index
// / child-page indirection (Google was unhappy with the two-tier setup, and the
// curated photo set is far below the protocol's 50,000-URL / 50MB per-file cap).
// Dynamic (queries a live list), so it must not be prerendered at build (the root
// +layout.ts sets prerender = true, which would snapshot an empty list when the
// API is unreachable during the Docker build).
export const prerender = false;

// Protocol cap of URLs per sitemap file. If the curated set ever approaches this,
// reintroduce a sitemap index of fixed-size child pages.
const MAX_URLS = 50000;

const STATIC_PATHS = ['/about', '/contact', '/privacy', '/terms', '/licensing', '/download', '/bestof', '/activity'];

function escapeXml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

function urlTag(path: string, lastmod?: string | null): string {
	const loc = escapeXml(`${HILLVIEW_BASE_URL}${path}`);
	return lastmod
		? `  <url><loc>${loc}</loc><lastmod>${escapeXml(lastmod)}</lastmod></url>`
		: `  <url><loc>${loc}</loc></url>`;
}

export const GET: RequestHandler = async ({ fetch }) => {
	// Newest public upload time → <lastmod> on /activity, so crawlers recrawl the
	// "new stuff appears here" feed promptly. Mirrors what the feed shows, incl. the
	// non-curated uploads the per-photo entries below deliberately omit.
	let activityLastmod: string | null = null;
	try {
		const res = await fetch(`${backendInternalUrl}/activity/recent?limit=1`);
		if (res.ok) {
			const { photos } = await res.json();
			activityLastmod = photos?.[0]?.uploaded_at ?? null;
		} else {
			console.error('sitemap: /activity/recent HTTP', res.status);
		}
	} catch (e) {
		console.error('sitemap: failed to fetch activity lastmod', e);
	}

	const entries: string[] = STATIC_PATHS.map((p) =>
		p === '/activity' ? urlTag(p, activityLastmod) : urlTag(p)
	);

	try {
		const res = await fetch(`${backendInternalUrl}/photos/sitemap-ids?limit=${MAX_URLS}`);
		if (res.ok) {
			const { total, photos } = await res.json();
			for (const p of photos as Array<{ uid: string; lastmod: string | null }>) {
				entries.push(urlTag(`/photo/${p.uid}`, p.lastmod));
			}
			if ((total ?? 0) > photos.length) {
				console.error(
					`sitemap: ${total} curated photos exceed the ${MAX_URLS}-URL cap; ${total - photos.length} omitted — reintroduce a sitemap index`
				);
			}
		} else {
			console.error('sitemap: /photos/sitemap-ids HTTP', res.status);
		}
	} catch (e) {
		console.error('sitemap: failed to fetch photo ids', e);
	}

	const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries.join('\n')}
</urlset>`;

	return new Response(xml, {
		headers: {
			'Content-Type': 'application/xml',
			'Cache-Control': 'max-age=3600',
		},
	});
};
