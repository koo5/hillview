import { writable, get } from 'svelte/store';
import { backendUrl } from './config';
import { spatialState } from './mapState';

export interface FeaturedPhotoData {
	id: string;
	latitude: number;
	longitude: number;
	bearing: number | null;
	description?: string | null;
}

// Holds the featured photo returned by the backend on a true first visit.
// Subscribers react to its transition from null → data and navigate the map.
export const featuredPhotoData = writable<FeaturedPhotoData | null>(null);

/**
 * Fire-and-forget fetch of the "featured photo near you" on a true first visit.
 * No-op for returning visitors (spatialState.ts is already defined from localStorage
 * or from a URL-param-driven init).
 */
export function maybeFetchFeaturedPhoto(): void {
	if (get(spatialState).ts !== undefined) return;
	fetch(`${backendUrl}/featured/nearest`)
		.then(r => (r.ok ? r.json() : null))
		.then(data => {
			if (data?.photo) featuredPhotoData.set(data.photo);
		})
		.catch(err => console.warn('🢄Featured: failed to fetch featured photo:', err));
}
