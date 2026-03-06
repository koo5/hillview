/**
 * Update Kotlin local DB with photo statuses learned from server.
 */

import { invoke } from '@tauri-apps/api/core';
import { TAURI } from './tauri';

export interface PhotoStatus {
	id: string;
	processing_status: string;
	error: string | null;
}

interface UpdatePhotoStatusesResult {
	success: boolean;
	updated_count?: number;
	error?: string;
}

/**
 * Update local Kotlin DB with photo statuses from server response.
 * Call this after fetching photos for "my photos" page.
 */
export async function updateKotlinPhotoStatuses(statuses: PhotoStatus[]): Promise<number> {
	if (!TAURI || statuses.length === 0) {
		return 0;
	}

	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'update_photo_statuses',
			params: { statuses }
		}) as UpdatePhotoStatusesResult;

		if (!result.success) {
			console.error('Failed to update photo statuses:', result.error);
			return 0;
		}

		return result.updated_count || 0;
	} catch (err) {
		console.error('Error updating photo statuses:', err);
		return 0;
	}
}
