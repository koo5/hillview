import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { backendInternalUrl } from '$lib/config.server';
import { parsePhotoUidParts } from '$lib/urlUtilsServer';
import type { PublicPhoto, PhotoAnnotation } from '$lib/photoDisplay';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const photoUid = params.uid;
	const parts = parsePhotoUidParts(photoUid);
	if (!parts || parts.source !== 'hillview') {
		throw error(404, 'Photo not found');
	}

	const publicUrl = `${backendInternalUrl}/photos/public/${encodeURIComponent(photoUid)}`;
	const annotationsUrl = `${backendInternalUrl}/annotations/photos/${encodeURIComponent(parts.id)}`;

	const [publicRes, annotationsRes] = await Promise.all([
		fetch(publicUrl),
		fetch(annotationsUrl),
	]);

	if (publicRes.status === 404) {
		throw error(404, 'Photo not found');
	}
	if (!publicRes.ok) {
		console.error('photo/[uid] SSR: public endpoint HTTP', publicRes.status);
		throw error(502, 'Failed to load photo');
	}

	const photo: PublicPhoto = await publicRes.json();
	const annotations: PhotoAnnotation[] = annotationsRes.ok ? await annotationsRes.json() : [];

	return { photo, annotations };
};
