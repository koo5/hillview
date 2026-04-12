import type { RequestHandler } from './$types';
import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
import { backendUrl } from '$lib/config';

const STATIC_PATHS = ['/about', '/contact', '/privacy', '/terms', '/download'];

export const GET: RequestHandler = async () => {
	const photos = await fetchBestOfPhotos();

	const urls = [
		...STATIC_PATHS.map((path) => `  <url><loc>${HILLVIEW_BASE_URL}${path}</loc></url>`),
		...photos.map((p) => {
			let loc = `${HILLVIEW_BASE_URL}/?lat=${p.latitude}&lon=${p.longitude}&zoom=18`;
			if (p.bearing != null) loc += `&bearing=${p.bearing}`;
			loc += `&photo=hillview-${p.id}`;
			return `  <url><loc>${loc}</loc></url>`;
		}),
	];

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

async function fetchBestOfPhotos(): Promise<{ id: string; latitude: number; longitude: number; bearing?: number }[]> {
	try {
		const response = await fetch(`${backendUrl}/bestof/photos?limit=40`);
		if (!response.ok) return [];
		const data = await response.json();
		return data.photos || [];
	} catch (e) {
		console.error('sitemap: failed to fetch bestof photos:', e);
		return [];
	}
}
