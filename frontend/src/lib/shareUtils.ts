/**
 * Shared photo sharing utility
 * Used by PhotoActionsMenu and OpenSeadragonViewer (ZoomView)
 */

import { constructShareUrl } from '$lib/urlUtils';
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
 * Share a photo using native sharing (Tauri) or clipboard fallback (web).
 * Returns a result with a user-facing message and error flag.
 */
export async function sharePhoto(photo: PhotoData | any, zoomViewBounds?: { x1: number; y1: number; x2: number; y2: number }): Promise<ShareResult> {
	if (!photo) return { message: '', error: false };

	try {
		const shareUrl = constructShareUrl(photo, zoomViewBounds);
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
