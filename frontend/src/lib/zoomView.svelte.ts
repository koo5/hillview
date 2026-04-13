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
	description?: string;
	width?: number;
	height?: number;
	photo_id?: string;     // For fetching annotations
	pyramid?: PyramidMetadata;  // DZI pyramid metadata (when available)
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
}

/** Set when page loads with x1/y1/x2/y2 URL params — signals zoom view
 *  should open once photo data becomes available. */
export const pendingZoomView = writable<ZoomViewInitialBounds | null>(null);

/** Reactive viewport bounds emitted by OSD viewer for URL sync. */
export const zoomViewportBounds = writable<ZoomViewInitialBounds | null>(null);