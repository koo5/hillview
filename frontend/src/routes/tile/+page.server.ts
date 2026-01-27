import { backendUrl } from '$lib/config';
import type { PageServerLoad } from './$types';

export const prerender = false;

export const load: PageServerLoad = async ({ fetch }) => {
	const response = await fetch(`${backendUrl}/activity/recent?limit=100`);
	const data = await response.json();
	return { photos: data.photos };
};
