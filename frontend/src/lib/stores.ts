import { writable } from 'svelte/store';
import { localStorageSharedStore } from './svelte-shared-store';
import type { DevicePhotoMetadata } from './photoCapture';

export interface UserPhoto {
    id: number;
    filename: string;  // Secure filename for storage
    original_filename: string;  // Original filename for display
    latitude: number;
    longitude: number;
    compass_angle?: number;
    altitude?: number;
    description?: string;
    is_public: boolean;
    created_at: string;
    updated_at: string;
    thumbnail_url?: string;
    uploaded_at?: string;
    captured_at?: string;
    sizes?: Record<string, { url: string; width: number; height: number; path?: string }>;
}

// Shared stores that can be imported by both auth and data modules
export const userPhotos = writable<UserPhoto[]>([]);

// Store for device-captured photos (loaded from backend)
export const devicePhotos = writable<DevicePhotoMetadata[]>([]);

// Store for photo capture settings
export const photoCaptureSettings = localStorageSharedStore('photoCaptureSettings', {
    hideFromGallery: false // Default to false (photos visible in gallery)
});
