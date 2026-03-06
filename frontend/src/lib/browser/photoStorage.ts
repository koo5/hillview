// Browser-specific photo storage using IndexedDB
// Provides persistent storage for photos captured in the browser
// Integrates with existing capture queue and upload system

import { writable, get } from 'svelte/store';
import type { CaptureLocation } from '../captureQueue';

const DB_NAME = 'HillviewPhotoDB';
const DB_VERSION = 4;
const PHOTO_STORE = 'photos';

// Export function to check background sync support
export function isBackgroundSyncSupported(): boolean {
    return 'serviceWorker' in navigator && 'sync' in ServiceWorkerRegistration.prototype;
}

export interface StoredPhoto {
    id: string;
    blob: Blob;
    width: number;
    height: number;
    metadata: {
        location: CaptureLocation;
        captured_at: number;
        orientation_code: number; // EXIF orientation (1, 3, 6, 8)
    };
    status: 'pending' | 'uploading' | 'uploaded' | 'failed';
    retry_count: number;
    last_error?: string;
    uploaded_at?: number;
    server_photo_id?: string;
    added_at: number;
    retry_after?: number;
}

// Store for tracking storage usage
export const browserStorageUsage = writable<{
    used: number;
    quota: number;
    percentage: number;
    photoCount: number;
}>({
    used: 0,
    quota: 0,
    percentage: 0,
    photoCount: 0
});

// Store for tracking upload queue status
export const browserUploadQueueStatus = writable<{
    pending: number;
    uploading: number;
    uploaded: number;
    failed: number;
}>({
    pending: 0,
    uploading: 0,
    uploaded: 0,
    failed: 0
});

class BrowserPhotoStorage {
    private db: IDBDatabase | null = null;
    private isInitialized = false;
    private readonly LOG_PREFIX = '🢄[BrowserPhotoStorage]';

    async init(): Promise<void> {
        if (this.isInitialized) return;

        try {
            this.db = await this.openDatabase();
            this.isInitialized = true;
            await this.updateStorageStats();
            await this.updateQueueStatus();
            console.log(`${this.LOG_PREFIX} Database initialized`);

            // Request persistent storage to prevent browser from deleting our data
            await this.requestPersistentStorage();
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to initialize database:`, error);
            throw error;
        }
    }

    private openDatabase(): Promise<IDBDatabase> {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                reject(new Error('Failed to open IndexedDB'));
            };

            request.onsuccess = () => {
                resolve(request.result);
            };

            request.onupgradeneeded = (event) => {
                const db = (event.target as IDBOpenDBRequest).result;

                // Migration: Remove old upload queue store if it exists
                if (db.objectStoreNames.contains('uploadQueue')) {
                    db.deleteObjectStore('uploadQueue');
                }

                // Create or upgrade photo store
                let photoStore: IDBObjectStore;
                if (!db.objectStoreNames.contains(PHOTO_STORE)) {
                    photoStore = db.createObjectStore(PHOTO_STORE, { keyPath: 'id' });
                } else {
                    photoStore = (event.target as IDBOpenDBRequest).transaction!.objectStore(PHOTO_STORE);
                }
                // Ensure all indexes exist
                if (!photoStore.indexNames.contains('status')) photoStore.createIndex('status', 'status');
                if (!photoStore.indexNames.contains('captured_at')) photoStore.createIndex('captured_at', 'metadata.captured_at');
                if (!photoStore.indexNames.contains('added_at')) photoStore.createIndex('added_at', 'added_at');
            };
        });
    }

    async savePhotoFromImageData(
        id: string,
        imageData: ImageData,
        metadata: {
            location: CaptureLocation;
            captured_at: number;
            orientation_code: number;
        }
    ): Promise<void> {
        if (!this.db) await this.init();

        console.log(`${this.LOG_PREFIX} Converting ImageData to Blob for photo ${id}`);

        // Convert ImageData to Blob using OffscreenCanvas (if available) or regular Canvas
        let blob: Blob;

        if (typeof OffscreenCanvas !== 'undefined') {
            // Use OffscreenCanvas for better performance
            const canvas = new OffscreenCanvas(imageData.width, imageData.height);
            const ctx = canvas.getContext('2d');
            if (!ctx) throw new Error('Failed to get canvas context');

            ctx.putImageData(imageData, 0, 0);
            blob = await canvas.convertToBlob({
                type: 'image/jpeg',
                quality: 0.95
            });
        } else {
            // Fallback to regular canvas
            const canvas = document.createElement('canvas');
            canvas.width = imageData.width;
            canvas.height = imageData.height;
            const ctx = canvas.getContext('2d');
            if (!ctx) throw new Error('Failed to get canvas context');

            ctx.putImageData(imageData, 0, 0);

            blob = await new Promise<Blob>((resolve, reject) => {
                canvas.toBlob(
                    (blob) => {
                        if (blob) resolve(blob);
                        else reject(new Error('Failed to convert canvas to blob'));
                    },
                    'image/jpeg',
                    0.95
                );
            });
        }

        await this.savePhoto(id, blob, imageData.width, imageData.height, metadata);
    }

    async savePhoto(
        id: string,
        blob: Blob,
        width: number,
        height: number,
        metadata: {
            location: CaptureLocation;
            captured_at: number;
            orientation_code: number;
        }
    ): Promise<void> {
        if (!this.db) await this.init();

        const storedPhoto: StoredPhoto = {
            id,
            blob,
            width,
            height,
            metadata,
            status: 'pending',
            retry_count: 0,
            added_at: Date.now()
        };

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');

        try {
            const photoStore = transaction.objectStore(PHOTO_STORE);
            await this.promisifyRequest(photoStore.put(storedPhoto));
            console.log(`${this.LOG_PREFIX} Photo saved: ${id}, size: ${blob.size} bytes`);
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to save photo:`, error);
            throw error;
        }

        // Update stats
        await this.updateStorageStats();
        await this.updateQueueStatus();

        // Trigger background sync if service worker is available
        await this.requestBackgroundSync();
    }

    async getNextPhotoForUpload(): Promise<StoredPhoto | null> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readonly');
        const photoStore = transaction.objectStore(PHOTO_STORE);

        // Get all pending and failed photos
        const pendingPhotos: StoredPhoto[] = [];

        // Get pending photos
        const pendingCursor = await this.promisifyRequest(
            photoStore.index('status').openCursor(IDBKeyRange.only('pending'))
        );
        if (pendingCursor) {
            await this.iterateCursor(pendingCursor, (photo) => {
                pendingPhotos.push(photo);
            });
        }

        // Get failed photos that are ready to retry
        const failedCursor = await this.promisifyRequest(
            photoStore.index('status').openCursor(IDBKeyRange.only('failed'))
        );
        if (failedCursor) {
            await this.iterateCursor(failedCursor, (photo) => {
                if (!photo.retry_after || photo.retry_after <= Date.now()) {
                    pendingPhotos.push(photo);
                }
            });
        }

        // Sort by added_at (older first)
        pendingPhotos.sort((a, b) => a.added_at - b.added_at);

        return pendingPhotos[0] || null;
    }

    private async iterateCursor(cursor: IDBCursorWithValue, callback: (value: StoredPhoto) => void): Promise<void> {
        return new Promise((resolve, reject) => {
            const processCursor = (cur: IDBCursorWithValue | null) => {
                if (!cur) {
                    resolve();
                    return;
                }
                callback(cur.value);
                cur.continue();
            };

            // The cursor's request object fires onsuccess for each iteration
            const request = cursor.request;
            request.onsuccess = () => processCursor(request.result as IDBCursorWithValue | null);
            request.onerror = () => reject(request.error);

            // Process the initial cursor value
            callback(cursor.value);
            cursor.continue();
        });
    }

    async markPhotoAsUploading(photoId: string): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTO_STORE);

        const photo = await this.promisifyRequest(store.get(photoId));
        if (photo) {
            photo.status = 'uploading';
            await this.promisifyRequest(store.put(photo));
        }

        await this.updateQueueStatus();
    }

    async markPhotoAsUploaded(photoId: string, serverPhotoId: string): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const photoStore = transaction.objectStore(PHOTO_STORE);

        const photo = await this.promisifyRequest(photoStore.get(photoId));
        if (photo) {
            photo.status = 'uploaded';
            photo.uploaded_at = Date.now();
            photo.server_photo_id = serverPhotoId;
            await this.promisifyRequest(photoStore.put(photo));
        }

        await this.updateQueueStatus();

        // Delete the blob after successful upload if storage is running low
        const usage = get(browserStorageUsage);
        if (usage.percentage > 50) {
            await this.deletePhotoBlob(photoId);
        }
    }

    async markPhotoAsFailed(photoId: string, error: string): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const photoStore = transaction.objectStore(PHOTO_STORE);

        const photo = await this.promisifyRequest(photoStore.get(photoId));
        if (photo) {
            photo.status = 'failed';
            photo.last_error = error;
            photo.retry_count = (photo.retry_count || 0) + 1;

            // Set retry delay with exponential backoff
            const retryDelay = Math.min(60000 * Math.pow(2, photo.retry_count - 1), 3600000); // Max 1 hour
            photo.retry_after = Date.now() + retryDelay;

            await this.promisifyRequest(photoStore.put(photo));
        }

        await this.updateQueueStatus();
    }

    async retryFailedUploads(): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const photoStore = transaction.objectStore(PHOTO_STORE);

        // Get all failed photos
        const failedPhotos = await this.promisifyRequest(
            photoStore.index('status').getAll('failed')
        );

        // Reset their status to pending and clear retry delay
        for (const photo of failedPhotos) {
            photo.status = 'pending';
            photo.retry_after = undefined;
            await this.promisifyRequest(photoStore.put(photo));
        }

        await this.updateQueueStatus();
        await this.requestBackgroundSync();
    }

    async deletePhoto(photoId: string): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const photoStore = transaction.objectStore(PHOTO_STORE);
        await this.promisifyRequest(photoStore.delete(photoId));

        await this.updateStorageStats();
        await this.updateQueueStatus();
    }

    async deletePhotoBlob(photoId: string): Promise<void> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTO_STORE);

        const photo = await this.promisifyRequest(store.get(photoId));
        if (photo && photo.status === 'uploaded') {
            // Keep metadata but remove the blob to save space
            photo.blob = new Blob([], { type: 'image/jpeg' });
            await this.promisifyRequest(store.put(photo));
            console.log(`${this.LOG_PREFIX} Deleted blob for uploaded photo ${photoId}`);
        }

        await this.updateStorageStats();
    }

    async getAllPhotos(): Promise<StoredPhoto[]> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readonly');
        const store = transaction.objectStore(PHOTO_STORE);
        return await this.promisifyRequest(store.getAll()) as StoredPhoto[];
    }

    async getPendingPhotos(): Promise<StoredPhoto[]> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readonly');
        const store = transaction.objectStore(PHOTO_STORE);
        const index = store.index('status');
        return await this.promisifyRequest(index.getAll('pending')) as StoredPhoto[];
    }

    async getPhotoCount(): Promise<number> {
        if (!this.db) await this.init();

        const transaction = this.db!.transaction([PHOTO_STORE], 'readonly');
        const store = transaction.objectStore(PHOTO_STORE);
        return await this.promisifyRequest(store.count()) as number;
    }

    private async updateStorageStats(): Promise<void> {
        if (!navigator.storage || !navigator.storage.estimate) {
            return;
        }

        try {
            const estimate = await navigator.storage.estimate();
            const photoCount = await this.getPhotoCount();

            browserStorageUsage.set({
                used: estimate.usage || 0,
                quota: estimate.quota || 0,
                percentage: estimate.quota ? ((estimate.usage || 0) / estimate.quota) * 100 : 0,
                photoCount
            });
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to estimate storage:`, error);
        }
    }

    private async updateQueueStatus(): Promise<void> {
        if (!this.db) return;

        const transaction = this.db.transaction([PHOTO_STORE], 'readonly');
        const store = transaction.objectStore(PHOTO_STORE);
        const index = store.index('status');

        const [pending, uploading, uploaded, failed] = await Promise.all([
            this.promisifyRequest(index.count('pending')),
            this.promisifyRequest(index.count('uploading')),
            this.promisifyRequest(index.count('uploaded')),
            this.promisifyRequest(index.count('failed'))
        ]);

        browserUploadQueueStatus.set({
            pending: pending as number,
            uploading: uploading as number,
            uploaded: uploaded as number,
            failed: failed as number
        });
    }

    async clearOldUploadedPhotos(daysToKeep: number = 7): Promise<void> {
        if (!this.db) await this.init();

        const cutoffTime = Date.now() - (daysToKeep * 24 * 60 * 60 * 1000);
        const transaction = this.db!.transaction([PHOTO_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTO_STORE);

        const photos = await this.promisifyRequest(store.getAll());

        for (const photo of photos) {
            if (photo.status === 'uploaded' &&
                photo.uploaded_at &&
                photo.uploaded_at < cutoffTime) {
                await this.promisifyRequest(store.delete(photo.id));
                console.log(`${this.LOG_PREFIX} Deleted old uploaded photo ${photo.id}`);
            }
        }

        await this.updateStorageStats();
        await this.updateQueueStatus();
    }

    async requestPersistentStorage(): Promise<boolean> {
        if (!navigator.storage || !navigator.storage.persist) {
            return false;
        }

        try {
            const isPersisted = await navigator.storage.persist();
            console.log(`${this.LOG_PREFIX} Persistent storage ${isPersisted ? 'granted' : 'denied'}`);
            return isPersisted;
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to request persistent storage:`, error);
            return false;
        }
    }

    async requestBackgroundSync(): Promise<void> {
        if (isBackgroundSyncSupported()) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await (registration as any).sync.register('photo-upload');
                console.log(`${this.LOG_PREFIX} Background sync requested`);
            } catch (error) {
                console.warn(`${this.LOG_PREFIX} Background sync not available:`, error);
            }
        }
    }

    private promisifyRequest<T = any>(request: IDBRequest<T>): Promise<T> {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
}

// Export singleton instance
export const browserPhotoStorage = new BrowserPhotoStorage();