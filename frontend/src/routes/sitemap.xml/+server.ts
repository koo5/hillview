import type { RequestHandler } from './$types';
import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
import { backendInternalUrl } from '$lib/config.server';
import { SITEMAP_PAGE_SIZE } from '$lib/sitemapConfig';

// Sitemap INDEX. robots.txt points crawlers here; it lists fixed-size child
// pages (/sitemap-photos.xml?page=N) so the photo set auto-paginates and never
// hits the 50k-URLs-per-file limit. Dynamic (queries a live count), so it must
// not be prerendered at build — see /sitemap-photos.xml for the per-page rule.
export const prerender = false;

function escapeXml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

export const GET: RequestHandler = async ({ fetch }) => {
	let pages = 1; // always advertise page 0 (it carries the static paths)
	try {
		const res = await fetch(`${backendInternalUrl}/photos/sitemap-ids?limit=0`);
		if (res.ok) {
			const { total } = await res.json();
			pages = Math.max(1, Math.ceil((total || 0) / SITEMAP_PAGE_SIZE));
		} else {
			console.error('sitemap index: /photos/sitemap-ids HTTP', res.status);
		}
	} catch (e) {
		console.error('sitemap index: failed to fetch total', e);
	}

	const children = Array.from({ length: pages }, (_, i) =>
		`  <sitemap><loc>${escapeXml(`${HILLVIEW_BASE_URL}/sitemap-photos.xml?page=${i}`)}</loc></sitemap>`
	);

	const xml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${children.join('\n')}
</sitemapindex>`;

	return new Response(xml, {
		headers: {
			'Content-Type': 'application/xml',
			'Cache-Control': 'max-age=3600',
		},
	});
};
