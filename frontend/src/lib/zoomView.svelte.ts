import { writable } from 'svelte/store';
import type { PyramidMetadata } from '$lib/types/photoCommon';
import { track } from '$lib/analytics';

/**
 * Store for managing full-screen photo zoom view state
 */

export interface ZoomViewData {
	fallback_url: string;  // Current thumbnail/preview URL
	url: string;           // Full-size image URL
	filename: string;
	title?: string;
	description?: string;
	width?: number;
	height?: number;
	photo_id?: string;     // For fetching annotations
	pyramid?: PyramidMetadata;  // DZI pyramid metadata (when available)
	equirectangular?: boolean;  // True for 360° panoramas
}

function createZoomViewStore() {
	const { subscribe, set, update } = writable<ZoomViewData | null>(null);
	return {
		subscribe,
		update,
		set: (value: ZoomViewData | null) => {
			if (value) track('zoomView', {id: value.photo_id ?? ''});
			set(value);
		}
	};
}

export const zoomViewData = createZoomViewStore();

/**
 * Viewport bounds in OSD coordinates (width normalized to 1.0).
 * Used to persist zoom/pan state in URL params.
 */
export interface ZoomViewInitialBounds {
	x1: number;
	y1: number;
	x2: number;
	y2: number;
	/** When set (URL ?photo= flow), the pending zoomview belongs to THIS photo
	 *  — the open bridge must not hijack it for whatever photo happens to come
	 *  in front. Absent for the pinch flow, where the front photo IS the one
	 *  being pinched. */
	photoUid?: string;
}

/** Set when page loads with x1/y1/x2/y2 URL params — signals zoom view
 *  should open once photo data becomes available. */
export const pendingZoomView = writable<ZoomViewInitialBounds | null>(null);

/** Verdict on a URL-requested photo that will never arrive (e.g. deleted —
 *  the public-endpoint probe in Map.svelte 404ed). The pending overlay shows
 *  this instead of spinning forever. */
export const pendingZoomViewError = writable<string | null>(null);

/** Reactive viewport bounds emitted by OSD viewer for URL sync. */
export const zoomViewportBounds = writable<ZoomViewInitialBounds | null>(null);