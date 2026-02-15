// Simple upload manager for browser photos
// Handles uploading photos from IndexedDB to server

import { photoStorage, type BrowserPhoto } from './photoStorage';
import { secureUploadFiles } from '../secureUpload';
import { writable, get } from 'svelte/store';

export interface UploadStatus {
    isUploading: boolean;
    currentPhotoId: string | null;
    pendingCount: number;
    successCount: number;
    failureCount: number;
}

export const uploadStatus = writable<UploadStatus>({
    isUploading: false,
    currentPhotoId: null,
    pendingCount: 0,
    successCount: 0,
    failureCount: 0
});

export class PhotoUploadManager {
    private readonly LOG_PREFIX = '🢄[PhotoUpload]';
    private isRunning = false;
    private maxRetries = 3;

    async uploadPending(): Promise<void> {
        if (this.isRunning) {
            console.log(`${this.LOG_PREFIX} Already uploading`);
            return;
        }

        this.isRunning = true;

        try {
            const pendingPhotos = await photoStorage.getPendingUploads();

            uploadStatus.update(s => ({
                ...s,
                pendingCount: pendingPhotos.length,
                successCount: 0,
                failureCount: 0
            }));

            console.log(`${this.LOG_PREFIX} Found ${pendingPhotos.length} pending uploads`);

            for (const photo of pendingPhotos) {
                if (!navigator.onLine) {
                    console.log(`${this.LOG_PREFIX} Offline, stopping upload`);
                    break;
                }

                await this.uploadPhoto(photo);
            }

        } finally {
            this.isRunning = false;
            uploadStatus.update(s => ({
                ...s,
                isUploading: false,
                currentPhotoId: null
            }));
        }
    }

    private async uploadPhoto(photo: BrowserPhoto): Promise<void> {
        // Skip if already tried too many times
        if (photo.upload_attempts >= this.maxRetries) {
            console.log(`${this.LOG_PREFIX} Skipping ${photo.id} - too many attempts`);
            return;
        }

        uploadStatus.update(s => ({
            ...s,
            isUploading: true,
            currentPhotoId: photo.id
        }));

        console.log(`${this.LOG_PREFIX} Uploading photo ${photo.id}`);

        try {
            // Create File object from blob
            const file = new File(
                [photo.blob],
                `${photo.id}.jpg`,
                { type: 'image/jpeg' }
            );

            // Add EXIF-like metadata as description for now
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

            const description = JSON.stringify(metadata);

            // Use existing secure upload
            const result = await secureUploadFiles(
                [file],
                description,
                true, // isPublic
                undefined,
                undefined,
                (file, error) => {
                    console.error(`${this.LOG_PREFIX} Upload error for ${file.name}:`, error);
                }
            );

            if (result.successCount > 0) {
                await photoStorage.markUploaded(photo.id);

                uploadStatus.update(s => ({
                    ...s,
                    successCount: s.successCount + 1,
                    pendingCount: Math.max(0, s.pendingCount - 1)
                }));

                console.log(`${this.LOG_PREFIX} Successfully uploaded ${photo.id}`);

                // Optionally delete from storage to save space
                if (await this.shouldDeleteAfterUpload()) {
                    await photoStorage.delete(photo.id);
                    console.log(`${this.LOG_PREFIX} Deleted ${photo.id} after upload`);
                }
            } else {
                throw new Error(result.results[0]?.error || 'Upload failed');
            }

        } catch (error) {
            await photoStorage.incrementUploadAttempts(photo.id);

            uploadStatus.update(s => ({
                ...s,
                failureCount: s.failureCount + 1
            }));

            console.error(`${this.LOG_PREFIX} Failed to upload ${photo.id}:`, error);
        }
    }

    private async shouldDeleteAfterUpload(): Promise<boolean> {
        // Check storage usage
        const estimate = await photoStorage.getStorageEstimate();
        const usagePercent = (estimate.used / estimate.quota) * 100;

        // Delete if using more than 50% of quota
        return usagePercent > 50;
    }

    async retryFailed(): Promise<void> {
        // Reset upload attempts for failed photos
        const photos = await photoStorage.getPendingUploads();

        for (const photo of photos) {
            if (photo.upload_attempts > 0) {
                photo.upload_attempts = 0;
                await photoStorage.save(photo);
            }
        }

        // Try uploading again
        await this.uploadPending();
    }
}

export const uploadManager = new PhotoUploadManager();