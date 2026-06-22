import type { RequestHandler } from './$types';
import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
import { backendInternalUrl } from '$lib/config.server';
import { SITEMAP_PAGE_SIZE } from '$lib/sitemapConfig';

// A single child page of the sitemap index (/sitemap.xml), selected by ?page=N.
// Page 0 also carries the static pages. Dynamic — must not be prerendered at
// build (the root +layout.ts sets prerender = true, which would snapshot an
// empty list when the API is unreachable during the Docker build).
export const prerender = false;

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

export const GET: RequestHandler = async ({ fetch, url }) => {
	const page = Math.max(0, parseInt(url.searchParams.get('page') ?? '0', 10) || 0);

	// Static paths ride on page 0 so the index doesn't need a separate entry.
	const entries: string[] = page === 0 ? STATIC_PATHS.map((p) => urlTag(p)) : [];

	try {
		const res = await fetch(
			`${backendInternalUrl}/photos/sitemap-ids?offset=${page * SITEMAP_PAGE_SIZE}&limit=${SITEMAP_PAGE_SIZE}`
		);
		if (res.ok) {
			const { photos } = await res.json();
			for (const p of photos as Array<{ uid: string; lastmod: string | null }>) {
				entries.push(urlTag(`/photo/${p.uid}`, p.lastmod));
			}
		} else {
			console.error('sitemap page: /photos/sitemap-ids HTTP', res.status);
		}
	} catch (e) {
		console.error('sitemap page: failed to fetch photo ids', e);
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
