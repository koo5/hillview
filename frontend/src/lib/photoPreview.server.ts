/** Public metadata for map and short-link previews; failures keep the site card. */
import { backendInternalUrl } from '$lib/config.server';
import { parsePhotoUid, parsePhotoUidParts } from '$lib/urlUtilsServer';
import type { PublicPhoto, PhotoAnnotation } from '$lib/photoDisplay';
import { ssrAuthHeaders } from '$lib/ssrAuth.server';

export async function loadPhotoPreview(
	photoParam: string | null,
	fetch: typeof globalThis.fetch,
	locals: App.Locals
): Promise<{ photo: PublicPhoto | null; annotations: PhotoAnnotation[] }> {
	const photoUid = parsePhotoUid(photoParam);
	const parts = photoUid ? parsePhotoUidParts(photoUid) : null;
	if (!photoUid || !parts || parts.source !== 'hillview') {
		return { photo: null, annotations: [] };
	}

	const publicUrl = `${backendInternalUrl}/photos/public/${encodeURIComponent(photoUid)}`;
	const annotationsUrl = `${backendInternalUrl}/annotations/photos/${encodeURIComponent(parts.id)}`;

	try {
		// The ticket buys little here — these fetches feed head tags, and the
		// crawlers they exist for never carry one — but sending it keeps hidden
		// content hidden: a photo this visitor hid should not title their tab.
		// No viewer_id is returned: nothing on this page corrects itself client-side.
		const headers = ssrAuthHeaders(locals);
		const [publicRes, annotationsRes] = await Promise.all([
			fetch(publicUrl, { headers }),
			fetch(annotationsUrl, { headers }),
		]);

		if (!publicRes.ok) {
			if (publicRes.status !== 404) {
				console.error('Photo preview: public endpoint HTTP', publicRes.status);
			}
			return { photo: null, annotations: [] };
		}

		const photo: PublicPhoto = await publicRes.json();
		const annotations: PhotoAnnotation[] = annotationsRes.ok ? await annotationsRes.json() : [];
		return { photo, annotations };
	} catch (err) {
		console.error('Photo preview fetch failed:', err);
		return { photo: null, annotations: [] };
	}
}
