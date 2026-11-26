import { backendUrl } from '$lib/config';

export interface PlaceResult {
	id: string;
	name: string;
	display_name: string;
	lat: number;
	lon: number;
	/** South, north, west, east. */
	bounds: [number, number, number, number] | null;
}

export async function searchPlaces(query: string, signal: AbortSignal): Promise<PlaceResult[]> {
	const params = new URLSearchParams({ q: query.trim() });
	const response = await fetch(`${backendUrl}/places/search?${params}`, { signal });
	if (!response.ok) {
		throw new Error(response.status === 504
			? 'Place search timed out. Please try again.'
			: 'Place search is temporarily unavailable. Please try again.');
	}
	return response.json();
}
