// Upload manager for browser photos
// Handles uploading photos from IndexedDB to server.
// The upload loop is shared between foreground (main thread) and
// background (service worker) contexts via uploadPendingPhotos().

import { browserPhotoStorage, type StoredPhoto } from './photoStorage';
import { writable } from 'svelte/store';

const LOG_PREFIX = '🢄[PhotoUpload]';
const MAX_RETRIES = 3;

export interface UploadResult {
    success: boolean;
    photo_id?: string;
    error?: string;
}

/** Function that uploads a single photo and returns a result */
export type PhotoUploader = (photo: StoredPhoto) => Promise<UploadResult>;

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

let isRunning = false;

/**
 * Shared upload loop used by both foreground and background sync.
 * Iterates pending photos, uploads each via the provided uploader function,
 * and updates status in IndexedDB.
 */
export async function uploadPendingPhotos(uploader: PhotoUploader): Promise<void> {
    if (isRunning) {
        console.log(`${LOG_PREFIX} Already uploading`);
        return;
    }

    isRunning = true;

    try {
        const pendingPhotos = await browserPhotoStorage.getPendingPhotos();

        uploadStatus.update(s => ({
            ...s,
            pendingCount: pendingPhotos.length,
            successCount: 0,
            failureCount: 0
        }));

        console.log(`${LOG_PREFIX} Found ${pendingPhotos.length} pending uploads`);

        for (const photo of pendingPhotos) {
            if (typeof navigator !== 'undefined' && !navigator.onLine) {
                console.log(`${LOG_PREFIX} Offline, stopping upload`);
                break;
            }

            if (photo.retry_count >= MAX_RETRIES) {
                console.log(`${LOG_PREFIX} Skipping ${photo.id} - too many attempts`);
                continue;
            }

            uploadStatus.update(s => ({
                ...s,
                isUploading: true,
                currentPhotoId: photo.id
            }));

            console.log(`${LOG_PREFIX} Uploading photo ${photo.id}`);

            try {
                await browserPhotoStorage.markPhotoAsUploading(photo.id);

                const result = await uploader(photo);

                if (result.success && result.photo_id) {
                    await browserPhotoStorage.markPhotoAsUploaded(photo.id, result.photo_id);

                    uploadStatus.update(s => ({
                        ...s,
                        successCount: s.successCount + 1,
                        pendingCount: Math.max(0, s.pendingCount - 1)
                    }));

                    console.log(`${LOG_PREFIX} Successfully uploaded ${photo.id}`);
                } else {
                    throw new Error(result.error || 'Upload failed');
                }
            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Unknown error';
                await browserPhotoStorage.markPhotoAsFailed(photo.id, errorMessage);

                uploadStatus.update(s => ({
                    ...s,
                    failureCount: s.failureCount + 1
                }));

                console.error(`${LOG_PREFIX} Failed to upload ${photo.id}:`, error);
            }
        }
    } finally {
        isRunning = false;
        uploadStatus.update(s => ({
            ...s,
            isUploading: false,
            currentPhotoId: null
        }));
    }
}

/** Retry failed uploads by resetting them to pending, then running the loop */
export async function retryFailed(uploader: PhotoUploader): Promise<void> {
    await browserPhotoStorage.retryFailedUploads();
    await uploadPendingPhotos(uploader);
}
