// Browser-side photo edits — web counterpart of the native edit queue
// (EditEntity + processPendingEdits on Android). The browser has no separate
// edits table; an edit is applied directly to the stored photo, which bumps
// its version and re-queues it for upload.

import { browserPhotoStorage, type StoredPhoto } from './photoStorage';
import type { AnonymizationState } from '$lib/photoAnonymizationMenu';

export type BrowserPhotoLookup =
	| { status: 'not-found' }
	| { status: 'file-missing' }
	| { status: 'ready'; photo: StoredPhoto; state: AnonymizationState };

/**
 * Find a photo in browser storage by server photo ID or local photo ID.
 * Distinguishes "never had it / deleted" from "had it but the blob was
 * evicted to save space after upload" — the latter can't be re-uploaded.
 */
export async function lookupBrowserPhoto(
	photoId: string | number,
	isServerPhoto: boolean
): Promise<BrowserPhotoLookup> {
	const photo = isServerPhoto
		? await browserPhotoStorage.getPhotoByServerPhotoId(String(photoId))
		: await browserPhotoStorage.getPhoto(String(photoId));

	if (!photo || photo.deleted) {
		return { status: 'not-found' };
	}
	if (!photo.blob || photo.blob.size === 0) {
		return { status: 'file-missing' };
	}
	return { status: 'ready', photo, state: getBrowserAnonymizationState(photo) };
}

/**
 * Derive the anonymization state from a stored photo's override:
 * null/absent = 'auto', "[]" = 'none', anything else = 'custom'.
 */
export function getBrowserAnonymizationState(photo: StoredPhoto): AnonymizationState {
	const override = photo.anonymization_override;
	if (override == null) return 'auto';
	try {
		const parsed = JSON.parse(override);
		if (Array.isArray(parsed) && parsed.length === 0) return 'none';
	} catch {
		// unparseable override — treat as custom
	}
	return 'custom';
}

/**
 * Apply an anonymization override to a browser photo and queue it for re-upload.
 * @param photoId - The local (IndexedDB) photo ID
 * @param value - null for auto-detect, [] for skip anonymization, or array of rectangles
 * @returns true if the photo existed and was updated
 */
export async function setBrowserAnonymizationOverride(
	photoId: string,
	value: null | any[]
): Promise<boolean> {
	const override = value === null ? null : JSON.stringify(value);
	return browserPhotoStorage.setAnonymizationOverride(photoId, override);
}
