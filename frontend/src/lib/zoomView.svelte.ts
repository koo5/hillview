import { writable } from 'svelte/store';

/**
 * Store for managing full-screen photo zoom view state
 */

export interface ZoomViewData {
	fallback_url: string;  // Current thumbnail/preview URL
	url: string;           // Full-size image URL
	filename: string;
	width?: number;
	height?: number;
}

export const zoomViewData = writable<ZoomViewData | null>(null);