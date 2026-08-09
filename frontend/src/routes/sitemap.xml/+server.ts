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

const STATIC_PATHS = ['/', '/about', '/contact', '/privacy', '/terms', '/licensing', '/download', '/bestof', '/activity'];

function escapeXml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

// img: absolute URL of the page's representative image, emitted as a Google
// image-sitemap extension entry (only <image:loc> — the other sub-tags were
// deprecated by Google in 2022 and are ignored). Cross-domain image hosts
// (pics.hillview.cz) are explicitly allowed by the protocol.
function urlTag(path: string, lastmod?: string | null, img?: string | null): string {
	const loc = escapeXml(`${HILLVIEW_BASE_URL}${path}`);
	const lastmodTag = lastmod ? `<lastmod>${escapeXml(lastmod)}</lastmod>` : '';
	const imgTag = img ? `<image:image><image:loc>${escapeXml(img)}</image:loc></image:image>` : '';
	return `  <url><loc>${loc}</loc>${lastmodTag}${imgTag}</url>`;
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
			for (const p of photos as Array<{ uid: string; lastmod: string | null; img?: string | null }>) {
				entries.push(urlTag(`/photo/${p.uid}`, p.lastmod, p.img));
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
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
${entries.join('\n')}
</urlset>`;

	return new Response(xml, {
		headers: {
			'Content-Type': 'application/xml',
			'Cache-Control': 'max-age=3600',
		},
	});
};
