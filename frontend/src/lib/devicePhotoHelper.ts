import { convertFileSrc } from '@tauri-apps/api/core';

/**
 * Convert device photo path to asset URL for off-main-thread loading
 * Uses Tauri's built-in asset protocol for file paths,
 * or returns content:// URIs directly (WebView can load these natively)
 */
export function getDevicePhotoUrl(path: string): string {
    // content:// URIs can be loaded directly by Android WebView
    if (path.startsWith('content://')) {
        return path;
    }

    // Remove "file://" prefix if present, as convertFileSrc expects just the path
    const cleanPath = path.startsWith('file://') ? path.slice(7) : path;

    // Convert to asset URL (synchronous, no async needed!)
    const assetUrl = convertFileSrc(cleanPath);

    return assetUrl;
}

/**
 * @deprecated No longer needed with convertFileSrc approach
 * Kept for backward compatibility during transition
 */
export function cleanupDevicePhotoCache() {
    // No-op: convertFileSrc doesn't require manual cleanup
}
