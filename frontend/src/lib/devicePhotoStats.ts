import { writable } from 'svelte/store';
import { invoke } from '@tauri-apps/api/core';
import { TAURI } from './tauri';

export interface DevicePhotoStats {
	total: number;
	pending: number;
	uploading: number;
	completed: number;
	failed: number;
}

export const devicePhotoStats = writable<DevicePhotoStats | null>(null);
export const devicePhotoStatsLoading = writable(false);
export const devicePhotoStatsError = writable<string | null>(null);

export async function fetchDevicePhotoStats(): Promise<DevicePhotoStats | null> {
	if (!TAURI) {
		return null;
	}

	devicePhotoStatsLoading.set(true);
	devicePhotoStatsError.set(null);

	try {
		const result = await invoke('plugin:hillview|cmd', {
			command: 'device_photos_stats',
			params: null
		}) as DevicePhotoStats;

		devicePhotoStats.set(result);
		return result;
	} catch (err) {
		console.error('Failed to fetch device photo stats:', err);
		devicePhotoStatsError.set(`${err}`);
		return null;
	} finally {
		devicePhotoStatsLoading.set(false);
	}
}

export function hasUploadsToRetry(stats: DevicePhotoStats | null): boolean {
	return stats !== null && (stats.pending > 0 || stats.failed > 0);
}
