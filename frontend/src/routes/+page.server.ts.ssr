import type { PageServerLoad } from './$types';
import { TAURI } from '$lib/tauri';
import { backendUrl } from '$lib/config';
import { parsePhotoUid } from '$lib/urlUtilsServer';

// Enable SSR for this route to generate OpenGraph metadata
export const ssr = !TAURI;
// Disable prerendering since we need dynamic URL parameters
export const prerender = false;

export const load: PageServerLoad = async ({ url, fetch }) => {
	// Skip OpenGraph fetching in Tauri (should not happen due to ssr = !TAURI, but double-check)
	if (TAURI) {
		console.log('🢄+page.server.ts: Skipping OpenGraph fetch in Tauri');
		return { photoMeta: null };
	}
	else
	{
		console.log('🢄+page.server.ts: Running OpenGraph fetch on server');
	}

	// Check for photo parameter in URL
	const photoParam = url.searchParams.get('photo');
	const photoUid = parsePhotoUid(photoParam);

	if (photoUid) {
		try {

			// Safely construct API URL with proper escaping
			const apiUrl = new URL(`http://api:8055/api/photos/share/${encodeURIComponent(photoUid)}`);
			console.log('Fetching photo metadata for OpenGraph from:', apiUrl.toString());
			const response = await fetch(apiUrl.toString());

			if (response.ok) {
				const photoMeta = await response.json();

				return {
					photoMeta: {
						description: photoMeta.description || 'Photo on Hillview',
						imageUrl: photoMeta.image_url,
						thumbnailUrl: photoMeta.thumbnail_url,
						width: photoMeta.width,
						height: photoMeta.height,
						latitude: photoMeta.latitude,
						longitude: photoMeta.longitude,
						capturedAt: photoMeta.captured_at,
						photoUid: photoUid
					}
				};
			}
			else {
				console.error('Failed to fetch photo metadata for OpenGraph: HTTP', response.status);
			}
		} catch (error) {
			console.error('Failed to fetch photo metadata for OpenGraph:', error);
		}
	}

	// Return default metadata if no photo or fetch failed
	return {
		photoMeta: null
	};
};
