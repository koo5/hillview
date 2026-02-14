import { Glasses, Smile } from 'lucide-svelte';
import { invoke } from '@tauri-apps/api/core';
import type { DropdownMenuItem } from '$lib/components/dropdown-menu/dropdownMenu.svelte';
import { addAlert } from '$lib/alertSystem.svelte';

/**
 * Look up the device photo ID from a server photo ID.
 * @param serverPhotoId - The server-assigned photo ID
 * @returns The device photo entity ID, or null if not found
 */
export async function getDevicePhotoIdByServerPhotoId(
	serverPhotoId: string | number
): Promise<string | null> {
	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'get_photo_id_by_server_photo_id',
			params: {
				server_photo_id: String(serverPhotoId)
			}
		}) as { success: boolean; photo_id?: string; error?: string };

		if (result.success && result.photo_id) {
			return result.photo_id;
		}
		return null;
	} catch (err) {
		console.error('Error looking up device photo ID:', err);
		return null;
	}
}

/**
 * Create an anonymization edit for a photo.
 * @param photoId - The device photo entity ID
 * @param value - null for auto-detect, [] for skip anonymization, or array of rectangles
 * @returns Promise with edit_id on success
 */
export async function createAnonymizationEdit(
	photoId: string,
	value: null | any[]
): Promise<{ success: boolean; edit_id?: number; error?: string }> {
	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'create_edit',
			params: {
				photo_id: photoId,
				action: 'set_anonymization_override',
				value: value
			}
		}) as { success: boolean; edit_id?: number; error?: string };

		return result;
	} catch (err) {
		console.error('Error creating anonymization edit:', err);
		return { success: false, error: String(err) };
	}
}

/**
 * Get the anonymization menu items for a photo.
 * Shows alerts on success/error using the standard alert system.
 * @param photoId - The device photo entity ID
 */
export function getAnonymizationMenuItems(photoId: string): DropdownMenuItem[] {
	const handleEdit = async (value: null | any[], label: string) => {
		const result = await createAnonymizationEdit(photoId, value);
		if (result.success && result.edit_id) {
			addAlert(`${label} - queued for re-upload`, 'success', {
				duration: 3000,
				source: 'anonymization-edit'
			});
		} else {
			addAlert(`Failed: ${result.error || 'Unknown error'}`, 'error', {
				duration: 5000,
				source: 'anonymization-edit'
			});
		}
	};

	return [
		{
			id: 'auto-anonymize',
			label: 'Auto-detect & blur',
			description: 'Detect faces and plates automatically',
			icon: Glasses,
			onclick: () => handleEdit(null, 'Auto-detect & blur'),
			testId: 'menu-auto-anonymize'
		},
		{
			id: 'skip-anonymization',
			label: 'No anonymization',
			description: 'Upload without blurring',
			icon: Smile,
			onclick: () => handleEdit([], 'No anonymization'),
			testId: 'menu-skip-anonymization'
		}
	];
}

/**
 * Get the anonymization menu items for a server photo.
 * Looks up the device photo ID first, then creates the edit.
 * Shows alerts on success/error using the standard alert system.
 * @param serverPhotoId - The server-assigned photo ID
 */
export function getAnonymizationMenuItemsForServerPhoto(serverPhotoId: string | number): DropdownMenuItem[] {
	const handleEdit = async (value: null | any[], label: string) => {
		// First, look up the device photo ID
		const devicePhotoId = await getDevicePhotoIdByServerPhotoId(serverPhotoId);
		if (!devicePhotoId) {
			addAlert('Photo not found on device - cannot change anonymization', 'error', {
				duration: 5000,
				source: 'anonymization-edit'
			});
			return;
		}

		const result = await createAnonymizationEdit(devicePhotoId, value);
		if (result.success && result.edit_id) {
			addAlert(`${label} - queued for re-upload`, 'success', {
				duration: 3000,
				source: 'anonymization-edit'
			});
		} else {
			addAlert(`Failed: ${result.error || 'Unknown error'}`, 'error', {
				duration: 5000,
				source: 'anonymization-edit'
			});
		}
	};

	return [
		{
			id: 'auto-anonymize',
			label: 'Auto-detect & blur',
			description: 'Detect faces and plates automatically',
			icon: Glasses,
			onclick: () => handleEdit(null, 'Auto-detect & blur'),
			testId: 'menu-auto-anonymize'
		},
		{
			id: 'skip-anonymization',
			label: 'No anonymization',
			description: 'Upload without blurring',
			icon: Smile,
			onclick: () => handleEdit([], 'No anonymization'),
			testId: 'menu-skip-anonymization'
		}
	];
}