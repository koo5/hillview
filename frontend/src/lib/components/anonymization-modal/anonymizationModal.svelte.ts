import { writable, get } from 'svelte/store';

export type AnonymizationModalState = {
	visible: boolean;
	photoId: string | number | null;
	/** If true, photoId is a server photo ID that needs lookup */
	isServerPhoto: boolean;
};

const initialState: AnonymizationModalState = {
	visible: false,
	photoId: null,
	isServerPhoto: false
};

export const anonymizationModalState = writable<AnonymizationModalState>(initialState);

/**
 * Open the anonymization options modal for a device photo.
 * @param photoId - The device photo entity ID
 */
export function openAnonymizationModal(photoId: string): void {
	anonymizationModalState.set({
		visible: true,
		photoId,
		isServerPhoto: false
	});
}

/**
 * Open the anonymization options modal for a server photo.
 * Will look up the device photo ID when an option is selected.
 * @param serverPhotoId - The server-assigned photo ID
 */
export function openAnonymizationModalForServerPhoto(serverPhotoId: string | number): void {
	anonymizationModalState.set({
		visible: true,
		photoId: serverPhotoId,
		isServerPhoto: true
	});
}

/**
 * Close the anonymization options modal.
 */
export function closeAnonymizationModal(): void {
	anonymizationModalState.set(initialState);
}

/**
 * Check if the modal is currently visible.
 */
export function isAnonymizationModalVisible(): boolean {
	return get(anonymizationModalState).visible;
}
