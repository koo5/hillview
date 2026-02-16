// Service worker upload functions that can be imported into the service worker
// This module handles uploading photos from IndexedDB in the background

import type { BrowserPhoto } from './photoStorage';

const DB_NAME = 'HillviewPhotoDB';
const PHOTOS_STORE = 'photos';
const AUTH_STORE = 'auth'; // Store for auth token

export class ServiceWorkerUploader {
    private readonly LOG_PREFIX = '[SW Upload]';

    async uploadPendingPhotos(): Promise<void> {
        console.log(`${this.LOG_PREFIX} Starting background upload`);

        try {
            const photos = await this.getPendingPhotos();
            console.log(`${this.LOG_PREFIX} Found ${photos.length} pending photos`);

            let successCount = 0;
            let failureCount = 0;

            for (const photo of photos) {
                // Skip if too many attempts
                if (photo.upload_attempts >= 3) {
                    console.log(`${this.LOG_PREFIX} Skipping photo ${photo.id} - too many attempts`);
                    continue;
                }

                const success = await this.uploadPhoto(photo);

                if (success) {
                    successCount++;
                    await this.markPhotoUploaded(photo.id);
                } else {
                    failureCount++;
                    await this.incrementUploadAttempts(photo.id);
                }

                // Small delay between uploads
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            console.log(`${this.LOG_PREFIX} Upload complete: ${successCount} success, ${failureCount} failed`);

            // If there were failures, register another sync for later
            if (failureCount > 0 && 'registration' in self) {
                const reg = self.registration as ServiceWorkerRegistration;
                if ('sync' in reg) {
                    await (reg.sync as any).register('photo-upload-retry');
                }
            }

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Upload error:`, error);
            throw error; // Re-throw to trigger sync retry
        }
    }

    private async uploadPhoto(photo: BrowserPhoto): Promise<boolean> {
        console.log(`${this.LOG_PREFIX} Uploading photo ${photo.id}`);

        try {
            const token = await this.getAuthToken();
            if (!token) {
                console.log(`${this.LOG_PREFIX} No auth token available, skipping upload`);
                return false;
            }

            // Create form data
            const formData = new FormData();

            // Create File from Blob
            const file = new File([photo.blob], `photo_${photo.id}.jpg`, {
                type: 'image/jpeg',
                lastModified: photo.captured_at
            });

            formData.append('files', file);

            // Add metadata
            const metadata = {
                latitude: photo.location.latitude,
                longitude: photo.location.longitude,
                altitude: photo.location.altitude,
                bearing: photo.location.bearing,
                accuracy: photo.location.accuracy,
                orientation_code: photo.orientation_code,
                captured_at: photo.captured_at,
                location_source: photo.location.location_source,
                bearing_source: photo.location.bearing_source
            };

            formData.append('description', JSON.stringify(metadata));
            formData.append('is_public', 'true');

            // Determine backend URL
            const backendUrl = self.location.hostname === 'localhost'
                ? 'http://localhost:8055'
                : self.location.origin;

            const response = await fetch(`${backendUrl}/api/photos/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });

            if (response.ok) {
                const result = await response.json();
                console.log(`${this.LOG_PREFIX} Photo ${photo.id} uploaded successfully`);
                return true;
            } else if (response.status === 401) {
                console.log(`${this.LOG_PREFIX} Auth token expired, clearing token`);
                await this.clearAuthToken();
                return false;
            } else {
                console.error(`${this.LOG_PREFIX} Upload failed: ${response.status} ${response.statusText}`);
                return false;
            }

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Upload error:`, error);
            return false;
        }
    }

    private async getPendingPhotos(): Promise<BrowserPhoto[]> {
        const db = await this.openDB();
        const transaction = db.transaction([PHOTOS_STORE], 'readonly');
        const store = transaction.objectStore(PHOTOS_STORE);
        const index = store.index('uploaded');

        return new Promise((resolve, reject) => {
            // Use IDBKeyRange to get all records where uploaded = false
            const range = IDBKeyRange.only(false);
            const request = index.getAll(range);
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    private async markPhotoUploaded(photoId: string): Promise<void> {
        const db = await this.openDB();
        const transaction = db.transaction([PHOTOS_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTOS_STORE);

        const photo = await new Promise<BrowserPhoto>((resolve, reject) => {
            const request = store.get(photoId);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });

        if (photo) {
            photo.uploaded = true;
            await new Promise((resolve, reject) => {
                const request = store.put(photo);
                request.onsuccess = () => resolve(undefined);
                request.onerror = () => reject(request.error);
            });
        }
    }

    private async incrementUploadAttempts(photoId: string): Promise<void> {
        const db = await this.openDB();
        const transaction = db.transaction([PHOTOS_STORE], 'readwrite');
        const store = transaction.objectStore(PHOTOS_STORE);

        const photo = await new Promise<BrowserPhoto>((resolve, reject) => {
            const request = store.get(photoId);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });

        if (photo) {
            photo.upload_attempts = (photo.upload_attempts || 0) + 1;
            await new Promise((resolve, reject) => {
                const request = store.put(photo);
                request.onsuccess = () => resolve(undefined);
                request.onerror = () => reject(request.error);
            });
        }
    }

    private async getAuthToken(): Promise<string | null> {
        try {
            const db = await this.openDB();

            // Check if auth store exists
            if (!db.objectStoreNames.contains(AUTH_STORE)) {
                console.log(`${this.LOG_PREFIX} Auth store doesn't exist`);
                return null;
            }

            const transaction = db.transaction([AUTH_STORE], 'readonly');
            const store = transaction.objectStore(AUTH_STORE);

            const token = await new Promise<any>((resolve, reject) => {
                const request = store.get('token');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });

            if (token && token.value && token.expires_at > Date.now()) {
                return token.value;
            }

            return null;
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to get auth token:`, error);
            return null;
        }
    }

    private async clearAuthToken(): Promise<void> {
        try {
            const db = await this.openDB();

            if (!db.objectStoreNames.contains(AUTH_STORE)) {
                return;
            }

            const transaction = db.transaction([AUTH_STORE], 'readwrite');
            const store = transaction.objectStore(AUTH_STORE);

            await new Promise((resolve, reject) => {
                const request = store.delete('token');
                request.onsuccess = () => resolve(undefined);
                request.onerror = () => reject(request.error);
            });
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to clear auth token:`, error);
        }
    }

    private openDB(): Promise<IDBDatabase> {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 2); // Version 2 to add auth store

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = (event.target as IDBOpenDBRequest).result;

                // Create photos store if needed
                if (!db.objectStoreNames.contains(PHOTOS_STORE)) {
                    const store = db.createObjectStore(PHOTOS_STORE, { keyPath: 'id' });
                    store.createIndex('uploaded', 'uploaded');
                    store.createIndex('captured_at', 'captured_at');
                    store.createIndex('created_at', 'created_at');
                }

                // Create auth store if needed
                if (!db.objectStoreNames.contains(AUTH_STORE)) {
                    db.createObjectStore(AUTH_STORE);
                }
            };
        });
    }
}

// Export for use in service worker
export const swUploader = new ServiceWorkerUploader();