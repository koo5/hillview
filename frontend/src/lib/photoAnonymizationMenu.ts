import { Glasses } from 'lucide-svelte';
import { invoke } from '@tauri-apps/api/core';
import type { DropdownMenuItem } from '$lib/components/dropdown-menu/dropdownMenu.svelte';
import type { Component } from 'svelte';
import { addAlert } from '$lib/alertSystem.svelte';
import { openAnonymizationModal, openAnonymizationModalForServerPhoto } from '$lib/components/anonymization-modal/anonymizationModal.svelte.js';

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
 * Check if the photo file exists on disk.
 * @param photoId - The device photo entity ID
 * @returns Object with exists boolean, or error
 */
export async function checkPhotoFileExists(
	photoId: string
): Promise<{ success: boolean; exists?: boolean; path?: string; error?: string }> {
	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'check_photo_file_exists',
			params: {
				photo_id: photoId
			}
		}) as { success: boolean; exists?: boolean; path?: string; error?: string };

		return result;
	} catch (err) {
		console.error('Error checking photo file exists:', err);
		return { success: false, error: String(err) };
	}
}

/**
 * Anonymization state types
 */
export type AnonymizationState = 'auto' | 'none' | 'custom';

export interface AnonymizationStateResult {
	success: boolean;
	state?: AnonymizationState;
	value?: null | string;
	error?: string;
}

/**
 * Get the current effective anonymization state for a photo.
 * This includes any pending edits that haven't been processed yet.
 * @param photoId - The device photo entity ID
 * @returns The current state: 'auto' (null), 'none' ([]), or 'custom' (manual rectangles)
 */
export async function getPhotoAnonymizationState(
	photoId: string
): Promise<AnonymizationStateResult> {
	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'get_photo_anonymization_state',
			params: {
				photo_id: photoId
			}
		}) as AnonymizationStateResult;

		return result;
	} catch (err) {
		console.error('Error getting photo anonymization state:', err);
		return { success: false, error: String(err) };
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
 * Trigger the upload loop to process pending edits and uploads.
 */
export async function triggerUploadLoop(): Promise<void> {
	try {
		await invoke('plugin:hillview|cmd', {
			command: 'retry_uploads',
			params: {}
		});
	} catch (err) {
		console.error('Error triggering upload loop:', err);
	}
}

/**
 * Get menu items for a device photo.
 * @param photoId - The device photo entity ID
 */
export function getPhotoMenuItems(photoId: string): DropdownMenuItem[] {
	return [
		{
			id: 'anonymization-options',
			label: 'Anonymization options',
			description: 'Change blur settings',
			icon: Glasses,
			onclick: () => openAnonymizationModal(photoId),
			testId: 'menu-anonymization-options'
		}
	];
}

/**
 * Get menu items for a server photo.
 * @param serverPhotoId - The server-assigned photo ID
 */
export function getPhotoMenuItemsForServerPhoto(serverPhotoId: string | number): DropdownMenuItem[] {
	return [
		{
			id: 'anonymization-options',
			label: 'Anonymization options',
			description: 'Change blur settings',
			icon: Glasses,
			onclick: () => openAnonymizationModalForServerPhoto(serverPhotoId),
			testId: 'menu-anonymization-options'
		}
	];
}
