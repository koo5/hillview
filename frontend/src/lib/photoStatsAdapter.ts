// Unified photo statistics adapter for both Tauri and Browser environments
// Provides consistent stats interface regardless of storage backend

import { writable, derived, get } from 'svelte/store';
import { invoke } from '@tauri-apps/api/core';
import { TAURI, BROWSER } from './tauri';
import { photoStorage } from './browser/photoStorage';
import { browserUploadQueueStatus, browserStorageUsage } from './browser/photoStorage';

export interface PhotoStats {
    total: number;
    pending: number;
    uploading: number;
    processing: number;
    completed: number;
    failed: number;
    deleted: number;
    // Additional platform-specific stats
    storageUsed?: number;
    storageQuota?: number;
    storagePercentage?: number;
}

// Platform-agnostic stats store
export const photoStats = writable<PhotoStats | null>(null);
export const photoStatsLoading = writable(false);
export const photoStatsError = writable<string | null>(null);

// Fetch stats based on current platform
export async function fetchPhotoStats(): Promise<PhotoStats | null> {
    photoStatsLoading.set(true);
    photoStatsError.set(null);

    try {
        if (BROWSER) {
            // Browser: Calculate stats from IndexedDB
            const photos = await photoStorage.getAll();
            const storageInfo = get(browserStorageUsage);
            const uploadStatus = get(browserUploadQueueStatus);

            const stats: PhotoStats = {
                total: photos.length,
                pending: uploadStatus.pending,
                uploading: uploadStatus.uploading,
                processing: 0, // Browser doesn't have separate processing state
                completed: uploadStatus.uploaded,
                failed: uploadStatus.failed,
                deleted: 0, // Could track if we implement soft delete
                // Browser-specific storage info
                storageUsed: storageInfo.used,
                storageQuota: storageInfo.quota,
                storagePercentage: storageInfo.percentage
            };

            photoStats.set(stats);
            return stats;

        } else if (TAURI) {
            // Tauri: Get from native plugin
            const result = await invoke('plugin:hillview|cmd', {
                command: 'device_photos_stats',
                params: null
            }) as PhotoStats;

            // Could also add device storage info here if available
            photoStats.set(result);
            return result;

        } else {
            // Neither platform detected
            photoStatsError.set('Platform not supported');
            return null;
        }

    } catch (err) {
        console.error('Failed to fetch photo stats:', err);
        photoStatsError.set(`${err}`);
        return null;
    } finally {
        photoStatsLoading.set(false);
    }
}

// Helper to check if there are uploads to retry
export function hasUploadsToRetry(stats: PhotoStats | null): boolean {
    return stats !== null && (
        stats.pending > 0 ||
        stats.failed > 0 ||
        stats.processing > 0 ||
        stats.uploading > 0
    );
}

// Auto-refresh stats when browser upload status changes
if (BROWSER) {
    browserUploadQueueStatus.subscribe(() => {
        // Debounce to avoid too many updates
        setTimeout(() => fetchPhotoStats(), 100);
    });
}

// Platform-specific storage info display helper
export function formatStorageInfo(stats: PhotoStats | null): string {
    if (!stats) return '';

    if (BROWSER && stats.storageUsed && stats.storageQuota) {
        const usedMB = (stats.storageUsed / 1024 / 1024).toFixed(1);
        const quotaMB = (stats.storageQuota / 1024 / 1024).toFixed(1);
        return `Storage: ${usedMB}MB / ${quotaMB}MB (${stats.storagePercentage?.toFixed(1)}%)`;
    } else if (TAURI) {
        // Could show device storage if available
        return `Device photos: ${stats.total}`;
    }

    return '';
}

// Get platform name for UI display
export function getPlatformName(): string {
    if (BROWSER) return 'Browser Storage';
    if (TAURI) return 'Device Storage';
    return 'Unknown Platform';
}