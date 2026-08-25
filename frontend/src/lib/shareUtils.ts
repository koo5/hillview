/**
 * Shared photo sharing utility
 * Used by PhotoActionsMenu and OpenSeadragonViewer (ZoomView)
 */

import { get } from 'svelte/store';
import { constructShareUrl, extractCoordinates, HILLVIEW_BASE_URL } from '$lib/urlUtils';
import { spatialState } from '$lib/mapState';
import { http } from '$lib/http';
import { TAURI } from '$lib/tauri';
import { invoke } from '@tauri-apps/api/core';
import type { PhotoData } from '$lib/sources';

function getUserName(photo: PhotoData | any): string | null {
	if (!photo) return null;
	if (photo.creator?.username) return photo.creator.username;
	if (photo.owner_username) return photo.owner_username;
	return null;
}

export interface ShareResult {
	message: string;
	error: boolean;
}

/**
 * Mint a short /shared/{slug} link on the backend. Returns null on any failure
 * so callers fall back to the long constructShareUrl() form.
 */
async function mintShortShareUrl(photo: PhotoData | any, zoomViewBounds?: { x1: number; y1: number; x2: number; y2: number }): Promise<string | null> {
	try {
		let photoUid = photo.uid;
		if (!photoUid && photo.id) {
			photoUid = `hillview-${photo.id}`;
		}
		if (!photoUid) return null;

		const coords = extractCoordinates(photo);
		const state = get(spatialState);
		const zoom = state?.zoom ? Math.min(22, Math.max(1, state.zoom)) : undefined;
		const bearing = coords?.bearing !== undefined && coords?.bearing !== null
			? ((coords.bearing % 360) + 360) % 360
			: undefined;

		const response = await http.post('/shared', {
			photo_uid: photoUid,
			zoom,
			lat: coords?.lat,
			lon: coords?.lon,
			bearing,
			zoom_view_bounds: zoomViewBounds ?? null
		});
		if (!response.ok) return null;

		const data = await response.json();
		if (!data?.slug) return null;
		return `${HILLVIEW_BASE_URL}/shared/${data.slug}`;
	} catch (error) {
		console.warn('🔗 Short share link minting failed, falling back to long URL:', error);
		return null;
	}
}

/**
 * The URL a share of this photo (and, optionally, zoom-view window) points
 * at: the short /shared/{slug} form when the backend mints one, else the long
 * parameterised map URL. Used by sharePhoto and by the zoom view's print QR.
 */
export async function buildShareUrl(photo: PhotoData | any, zoomViewBounds?: { x1: number; y1: number; x2: number; y2: number }): Promise<string> {
	return (await mintShortShareUrl(photo, zoomViewBounds)) ?? constructShareUrl(photo, zoomViewBounds);
}

/**
 * The shortest form of a share URL that still resolves: a /shared/{id}-{title}
 * slug loses its decorative title part (the resolver reads only the leading
 * id — SLUG_ID_RE in share_routes.py). For QR codes, where every byte is a
 * denser symbol; the copied/shared link keeps the readable slug. Any other
 * URL comes back unchanged.
 */
export function compactShareUrl(url: string): string {
	return url.replace(/(\/shared\/\d+)-[^/?#]*/, '$1');
}

/**
 * Share a photo using native sharing (Tauri) or clipboard fallback (web).
 * Returns a result with a user-facing message and error flag.
 */
export async function sharePhoto(photo: PhotoData | any, zoomViewBounds?: { x1: number; y1: number; x2: number; y2: number }): Promise<ShareResult> {
	if (!photo) return { message: '', error: false };

	try {
		const shareUrl = await buildShareUrl(photo, zoomViewBounds);
		const shareText = `Check out this photo on Hillview${getUserName(photo) ? ` by @${getUserName(photo)}` : ''}`;

		if (TAURI) {
			const result = await invoke('plugin:hillview|share_photo', {
				title: 'Photo on Hillview',
				text: shareText,
				url: shareUrl
			}) as { success: boolean; error?: string; message?: string };

			if (!result.success) {
				throw new Error(result.error || 'Share failed');
			}
			return { message: '', error: false };
		} else {
			const fullShareText = shareUrl//`${shareText}\n${shareUrl}`;
			if (navigator.clipboard) {
				await navigator.clipboard.writeText(fullShareText);
			} else {
				const textarea = document.createElement('textarea');
				textarea.value = fullShareText;
				document.body.appendChild(textarea);
				textarea.select();
				document.execCommand('copy');
				document.body.removeChild(textarea);
			}
			return { message: 'Share link copied to clipboard!', error: false };
		}
	} catch (error) {
		console.error('Error sharing photo:', error);
		return { message: 'Failed to share photo', error: true };
	}
}
