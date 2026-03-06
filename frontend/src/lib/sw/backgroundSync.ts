// Background Sync handler for photo uploads in the service worker context.
// Uses the shared upload loop from uploadManager with a SW-specific uploader
// that authenticates via IndexedDB tokens (no DOM/Svelte dependencies).

// SyncEvent is part of the Background Sync API but not in standard TS lib types.
// ExtendableEvent is also SW-only, so we define both locally.
interface SyncEvent extends Event {
    readonly tag: string;
    readonly lastChance: boolean;
    waitUntil(f: Promise<any>): void;
}

import { uploadPendingPhotos, type UploadResult, type PhotoUploader } from '$lib/browser/uploadManager';
import { swSecureUploader, swAuthFetch } from './serviceWorkerSecureUpload';
import type { StoredPhoto } from '$lib/browser/photoStorage';
import { clientCrypto } from '$lib/clientCrypto';
import { authStorage } from '$lib/browser/authStorage';
import { createSwStatusReporter } from './swStatusReporter';

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
        const reporter = createSwStatusReporter();
        event.waitUntil(
            uploadPendingPhotos(serviceWorkerUploader, { source: 'sw', reporter, authFetch: swAuthFetch }).then(() => {
                console.log(`${LOG_PREFIX} Background sync complete`);
            })
        );
    }
}
