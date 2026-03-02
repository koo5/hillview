// Background Sync handler for photo uploads in the service worker context.
// Uses the shared upload loop from uploadManager with a SW-specific uploader
// that authenticates via IndexedDB tokens (no DOM/Svelte dependencies).

import { uploadPendingPhotos, type UploadResult, type PhotoUploader } from '$lib/browser/uploadManager';
import { swSecureUploader } from './serviceWorkerSecureUpload';
import type { StoredPhoto } from '$lib/browser/photoStorage';

const LOG_PREFIX = '[SW BackgroundSync]';

/** Service worker uploader — uses IndexedDB auth tokens + direct fetch */
const serviceWorkerUploader: PhotoUploader = async (photo: StoredPhoto): Promise<UploadResult> => {
    const result = await swSecureUploader.uploadPhoto(photo);
    return {
        success: result.success,
        photo_id: result.photoId,
        error: result.error
    };
};

/** Handle sync events for photo uploads */
export function handleSync(event: SyncEvent): void {
    if (event.tag === 'photo-upload' || event.tag === 'photo-upload-retry') {
        event.waitUntil(
            uploadPendingPhotos(serviceWorkerUploader).then(() => {
                console.log(`${LOG_PREFIX} Background sync complete`);
            })
        );
    }
}
