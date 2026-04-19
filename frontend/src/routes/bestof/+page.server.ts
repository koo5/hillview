import type { PageServerLoad } from './$types';
import { backendInternalUrl } from '$lib/config.server';

export const load: PageServerLoad = async ({ fetch }) => {
	try {
		const apiUrl = new URL(`${backendInternalUrl}/bestof/photos`);
		apiUrl.searchParams.set('limit', '40');
		const response = await fetch(apiUrl.toString());

		if (!response.ok) {
			console.error('bestof SSR: backend returned HTTP', response.status);
			return { photos: [], has_more: false, next_cursor: null };
		}

		const data = await response.json();
		return {
			photos: data.photos ?? [],
			has_more: data.has_more ?? false,
			next_cursor: data.next_cursor ?? null
		};
	} catch (error) {
		console.error('bestof SSR: failed to fetch:', error);
		return { photos: [], has_more: false, next_cursor: null };
	}
};
