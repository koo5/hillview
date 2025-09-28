import { localStorageSharedStore } from './svelte-shared-store';

export interface UserPhoto {
    id: number;
    uid?: string;  // Cross-source unique identifier (hillview-{id})
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
    user_rating?: 'thumbs_up' | 'thumbs_down' | null;  // User's current rating
    rating_counts?: { thumbs_up: number; thumbs_down: number };  // Aggregate counts
}

// Store for photo capture settings
export const photoCaptureSettings = localStorageSharedStore('photoCaptureSettings', {
    hideFromGallery: false // Default to false (photos visible in gallery)
});
