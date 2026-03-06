// Upload manager for browser photos
// Handles uploading photos from IndexedDB to server.
// The upload loop is shared between foreground (main thread) and
// background (service worker) contexts via uploadPendingPhotos().

import { browserPhotoStorage, type StoredPhoto } from './photoStorage';
import { readSettings } from './settingsIndexedDb';
import { writable } from 'svelte/store';
import type { StatusReporter, SyncStatusReport } from '$lib/syncStatus';
import { syncProcessingPhotosStatus, type AuthFetch } from '$lib/uploadProtocol';

const LOG_PREFIX = '🢄[PhotoUpload]';

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
export interface UploadOptions {
    source?: 'sw' | 'fg';
    reporter?: StatusReporter;
    authFetch?: AuthFetch;
}

export async function uploadPendingPhotos(
    uploader: PhotoUploader,
    options?: UploadOptions
): Promise<void> {
    if (isRunning) {
        console.log(`${LOG_PREFIX} Already uploading`);
        return;
    }

    isRunning = true;
    const source = options?.source ?? 'fg';
    const report = options?.reporter;

    // Helper to build and emit a status report
    let successCount = 0;
    let failureCount = 0;
    let totalPending = 0;

    function emit(
        phase: SyncStatusReport['phase'],
        active: boolean,
        currentPhotoId: string | null = null,
        error?: string
    ) {
        if (!report) return;
        report({
            source,
            timestamp: Date.now(),
            active,
            phase,
            currentPhotoId,
            totalPending,
            successCount,
            failureCount,
            remainingCount: Math.max(0, totalPending - successCount - failureCount),
            error
        });
    }

    try {
        uploadStatus.update(s => ({
            ...s,
            successCount: 0,
            failureCount: 0
        }));

        emit('starting', true);

        // Fetch and upload one photo at a time (like Kotlin's upload loop).
        // New photos added during upload get picked up automatically.
        while (true) {
            if (typeof navigator !== 'undefined' && !navigator.onLine) {
                console.log(`${LOG_PREFIX} Offline, stopping upload`);
                break;
            }

            const settings = await readSettings();
            if (!settings?.auto_upload_enabled) {
                console.log(`${LOG_PREFIX} Auto-upload disabled, stopping upload loop`);
                break;
            }

            const photo = await browserPhotoStorage.getNextPhotoForUpload();
            if (!photo) {
                console.log(`${LOG_PREFIX} No more photos to upload`);
                break;
            }

            totalPending++;

            uploadStatus.update(s => ({
                ...s,
                isUploading: true,
                currentPhotoId: photo.id
            }));

            emit('uploading', true, photo.id);

            console.log(`${LOG_PREFIX} Uploading photo ${photo.id}`);

            try {
                const claimed = await browserPhotoStorage.tryClaimPhoto(photo.id);
                if (!claimed) {
                    console.log(`${LOG_PREFIX} Skipping ${photo.id} — already claimed by another context`);
                    continue;
                }

                const result = await uploader(photo);

                if (result.success && result.photo_id) {
                    await browserPhotoStorage.markPhotoAsUploaded(photo.id, result.photo_id);

                    successCount++;
                    uploadStatus.update(s => ({
                        ...s,
                        successCount: s.successCount + 1,
                        pendingCount: Math.max(0, s.pendingCount - 1)
                    }));

                    emit('uploading', true, photo.id);

                    console.log(`${LOG_PREFIX} Successfully uploaded ${photo.id}`);
                } else {
                    throw new Error(result.error || 'Upload failed');
                }
            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Unknown error';
                await browserPhotoStorage.markPhotoAsFailed(photo.id, errorMessage);

                failureCount++;
                uploadStatus.update(s => ({
                    ...s,
                    failureCount: s.failureCount + 1
                }));

                emit('uploading', true, photo.id, errorMessage);

                console.error(`${LOG_PREFIX} Failed to upload ${photo.id}:`, error);
            }
        }

        // Sync processing statuses with server (like Kotlin's syncProcessingPhotosStatus)
        if (options?.authFetch) {
            try {
                await syncProcessingPhotosStatus(options.authFetch);
            } catch (error) {
                console.warn(`${LOG_PREFIX} Processing status sync failed:`, error);
            }
        }

    } finally {
        isRunning = false;
        emit('finished', false);
        uploadStatus.update(s => ({
            ...s,
            isUploading: false,
            currentPhotoId: null
        }));
    }
}

/** Retry failed uploads by resetting them to pending, then running the loop */
export async function retryFailed(uploader: PhotoUploader, options?: UploadOptions): Promise<void> {
    await browserPhotoStorage.retryFailedUploads();
    await uploadPendingPhotos(uploader, options);
}
