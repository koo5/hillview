import { writable } from 'svelte/store';
import type { PyramidMetadata } from '$lib/types/photoCommon';

/**
 * Store for managing full-screen photo zoom view state
 */

export interface ZoomViewData {
	fallback_url: string;  // Current thumbnail/preview URL
	url: string;           // Full-size image URL
	filename: string;
	width?: number;
	height?: number;
	photo_id?: string;     // For fetching annotations
	pyramid?: PyramidMetadata;  // DZI pyramid metadata (when available)
}

export const zoomViewData = writable<ZoomViewData | null>(null);