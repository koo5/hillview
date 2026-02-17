// Simple upload manager for browser photos
// Handles uploading photos from IndexedDB to server

import { browserPhotoStorage, type StoredPhoto } from './photoStorage';
import { secureUploadFiles } from '../secureUpload';
import { writable } from 'svelte/store';

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
            const pendingPhotos = await browserPhotoStorage.getPendingPhotos();

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

    private async uploadPhoto(photo: StoredPhoto): Promise<void> {
        // Skip if already tried too many times
        if (photo.retry_count >= this.maxRetries) {
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
            // Mark as uploading
            await browserPhotoStorage.markPhotoAsUploading(photo.id);

            // Create File object from blob
            const file = new File(
                [photo.blob],
                `${photo.id}.jpg`,
                { type: 'image/jpeg' }
            );

            // Prepare metadata that browser can't write as EXIF
            const metadata = {
                latitude: photo.metadata.location.latitude,
                longitude: photo.metadata.location.longitude,
                altitude: photo.metadata.location.altitude,
                bearing: photo.metadata.location.bearing,
                accuracy: photo.metadata.location.accuracy,
                orientation_code: photo.metadata.orientation_code,
                captured_at: photo.metadata.captured_at,
                location_source: photo.metadata.location.location_source,
                bearing_source: photo.metadata.location.bearing_source
            };

            // Use existing secure upload with browser metadata
            const result = await secureUploadFiles(
                [file],
                undefined,  // description
                true,       // isPublic
                undefined,  // workerUrl
                undefined,  // onProgress
                (file, error) => {
                    console.error(`${this.LOG_PREFIX} Upload error for ${file.name}:`, error);
                },
                metadata    // browserMetadata
            );

            if (result.successCount > 0) {
                // Get the server photo ID from the result
                const serverPhotoId = result.results[0]?.photoId || photo.id;
                await browserPhotoStorage.markPhotoAsUploaded(photo.id, serverPhotoId);

                uploadStatus.update(s => ({
                    ...s,
                    successCount: s.successCount + 1,
                    pendingCount: Math.max(0, s.pendingCount - 1)
                }));

                console.log(`${this.LOG_PREFIX} Successfully uploaded ${photo.id}`);
            } else {
                throw new Error(result.results[0]?.error || 'Upload failed');
            }

        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            await browserPhotoStorage.markPhotoAsFailed(photo.id, errorMessage);

            uploadStatus.update(s => ({
                ...s,
                failureCount: s.failureCount + 1
            }));

            console.error(`${this.LOG_PREFIX} Failed to upload ${photo.id}:`, error);
        }
    }

    async retryFailed(): Promise<void> {
        // Reset failed photos to pending
        await browserPhotoStorage.retryFailedUploads();
        // Try uploading again
        await this.uploadPending();
    }
}

export const uploadManager = new PhotoUploadManager();