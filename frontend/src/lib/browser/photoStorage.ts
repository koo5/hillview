// Simple IndexedDB storage for photos captured in browser
// Focused on just storing and retrieving photos

import { writable } from 'svelte/store';
import type { CaptureLocation } from '../captureQueue';

const DB_NAME = 'HillviewPhotoDB';
const DB_VERSION = 1;
const PHOTOS_STORE = 'photos';

export interface BrowserPhoto {
    id: string;
    blob: Blob;
    location: CaptureLocation; // Contains lat, lng, heading (bearing), accuracy, etc.
    captured_at: number;
    orientation_code: number; // EXIF orientation (1, 3, 6, 8) - device rotation
    mode: 'slow' | 'fast';
    uploaded: boolean;
    upload_attempts: number;
    created_at: number;
}

export class PhotoStorage {
    private db: IDBDatabase | null = null;

    async open(): Promise<void> {
        if (this.db) return;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = (event.target as IDBOpenDBRequest).result;

                if (!db.objectStoreNames.contains(PHOTOS_STORE)) {
                    const store = db.createObjectStore(PHOTOS_STORE, { keyPath: 'id' });
                    store.createIndex('uploaded', 'uploaded');
                    store.createIndex('captured_at', 'captured_at');
                    store.createIndex('created_at', 'created_at');
                }
            };
        });
    }

    async save(photo: BrowserPhoto): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([PHOTOS_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTOS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.put(photo);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async get(id: string): Promise<BrowserPhoto | null> {
        await this.open();

        const transaction = this.db!.transaction([PHOTOS_STORE], 'readonly');
        const store = transaction.objectStore(PHOTOS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get(id);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
    }

    async getAll(): Promise<BrowserPhoto[]> {
        await this.open();

        const transaction = this.db!.transaction([PHOTOS_STORE], 'readonly');
        const store = transaction.objectStore(PHOTOS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    async getPendingUploads(): Promise<BrowserPhoto[]> {
        await this.open();

        const transaction = this.db!.transaction([PHOTOS_STORE], 'readonly');
        const store = transaction.objectStore(PHOTOS_STORE);

        // Get all photos and filter for non-uploaded ones
        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => {
                const allPhotos = request.result || [];
                const pending = allPhotos.filter(photo => !photo.uploaded);
                resolve(pending);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async markUploaded(id: string): Promise<void> {
        await this.open();

        const photo = await this.get(id);
        if (photo) {
            photo.uploaded = true;
            await this.save(photo);
        }
    }

    async incrementUploadAttempts(id: string): Promise<void> {
        await this.open();

        const photo = await this.get(id);
        if (photo) {
            photo.upload_attempts++;
            await this.save(photo);
        }
    }

    async delete(id: string): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([PHOTOS_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTOS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.delete(id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async deleteUploaded(): Promise<void> {
        const photos = await this.getAll();
        for (const photo of photos) {
            if (photo.uploaded) {
                await this.delete(photo.id);
            }
        }
    }

    async getStorageEstimate(): Promise<{ used: number; quota: number }> {
        if (navigator.storage && navigator.storage.estimate) {
            const estimate = await navigator.storage.estimate();
            return {
                used: estimate.usage || 0,
                quota: estimate.quota || 0
            };
        }
        return { used: 0, quota: 0 };
    }
}

// Export singleton
export const photoStorage = new PhotoStorage();

// Reactive stores for UI updates
export const browserUploadQueueStatus = writable({
    pending: 0,
    uploading: 0,
    uploaded: 0,
    failed: 0
});

export const browserStorageUsage = writable({
    used: 0,
    quota: 0,
    percentage: 0
});

// Update storage stats periodically
async function updateStorageStats() {
    const estimate = await photoStorage.getStorageEstimate();
    browserStorageUsage.set({
        used: estimate.used,
        quota: estimate.quota,
        percentage: estimate.quota > 0 ? (estimate.used / estimate.quota) * 100 : 0
    });
}

// Update upload queue status
async function updateQueueStatus() {
    const allPhotos = await photoStorage.getAll();
    const status = {
        pending: 0,
        uploading: 0,
        uploaded: 0,
        failed: 0
    };

    for (const photo of allPhotos) {
        if (photo.uploaded) {
            status.uploaded++;
        } else if (photo.upload_attempts > 3) {
            status.failed++;
        } else {
            status.pending++;
        }
    }

    browserUploadQueueStatus.set(status);
}

// Export update functions for external use
export async function refreshBrowserPhotoStats() {
    await updateStorageStats();
    await updateQueueStatus();
}

// Initialize stats on load
if (typeof window !== 'undefined') {
    updateStorageStats();
    updateQueueStatus();
}