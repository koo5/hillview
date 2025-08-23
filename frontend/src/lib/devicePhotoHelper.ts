import { invoke } from '@tauri-apps/api/core';

// Cache for device photo data URLs to avoid repeated file reads
const devicePhotoCache = new Map<string, string>();

export async function getDevicePhotoUrl(path: string): Promise<string> {
    // Check cache first
    if (devicePhotoCache.has(path)) {
        return devicePhotoCache.get(path)!;
    }

    try {
        // Read photo data from Tauri backend
        const photoData = await invoke<number[]>('read_device_photo', { path });
        const uint8Array = new Uint8Array(photoData);
        
        // Convert to blob and create data URL
        const blob = new Blob([uint8Array], { type: 'image/jpeg' });
        const dataUrl = URL.createObjectURL(blob);
        
        // Cache the result
        devicePhotoCache.set(path, dataUrl);
        
        return dataUrl;
    } catch (error) {
        console.error('🢄Failed to read device photo:', error);
        throw error;
    }
}

// Clean up cached URLs when component unmounts
export function cleanupDevicePhotoCache() {
    devicePhotoCache.forEach(url => URL.revokeObjectURL(url));
    devicePhotoCache.clear();
}