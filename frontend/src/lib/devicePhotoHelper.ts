import { convertFileSrc } from '@tauri-apps/api/core';

/**
 * Convert device photo path to asset URL for off-main-thread loading
 * Uses Tauri's built-in asset protocol for better performance
 */
export function getDevicePhotoUrl(path: string): string {
    // Remove "file://" prefix if present, as convertFileSrc expects just the path
    const cleanPath = path.startsWith('file://') ? path.slice(7) : path;

    // Convert to asset URL (synchronous, no async needed!)
    return convertFileSrc(cleanPath);
}

/**
 * @deprecated No longer needed with convertFileSrc approach
 * Kept for backward compatibility during transition
 */
export function cleanupDevicePhotoCache() {
    // No-op: convertFileSrc doesn't require manual cleanup
}