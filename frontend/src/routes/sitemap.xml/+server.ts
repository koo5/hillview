import type { RequestHandler } from './$types';
import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';

const STATIC_PATHS = ['/about', '/contact', '/privacy', '/terms', '/licensing', '/download', '/bestof'];

function escapeXml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

export const GET: RequestHandler = async () => {
	const urls = STATIC_PATHS.map(
		(path) => `  <url><loc>${escapeXml(`${HILLVIEW_BASE_URL}${path}`)}</loc></url>`
	);

	const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join('\n')}
</urlset>`;

	return new Response(sitemap, {
		headers: {
			'Content-Type': 'application/xml',
			'Cache-Control': 'max-age=3600',
		},
	});
};
