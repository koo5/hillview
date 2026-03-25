// Unified photo sync trigger
// Single entry point for triggering photo uploads, whether via
// Background Sync (service worker) or foreground (main thread).
// Uses a probe-then-fallback pattern: registers background sync,
// waits briefly for the SW to report activity, then falls back
// to foreground upload if the SW is unresponsive.

import { uploadPendingPhotos, type UploadResult } from './uploadManager';
import { isBackgroundSyncSupported, type StoredPhoto } from './photoStorage';
import { secureUploadFile, mainThreadAuthFetch } from '../secureUpload';
import { syncProcessingPhotosStatus } from '../uploadProtocol';
import { auth } from '../authStore';
import { getSettings } from '../settings';
import { get } from 'svelte/store';
import { initSyncStatusListener, isSwAlive, createFgStatusReporter } from '../syncStatus';

const LOG_PREFIX = '🢄[PhotoSync]';
const doLog = false;

/** Foreground uploader — uses the main-thread secure upload flow */
async function foregroundUploader(photo: StoredPhoto): Promise<UploadResult> {
    const file = new File(
        [photo.blob],
        `${photo.id}.jpg`,
        { type: 'image/jpeg' }
    );

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

    const result = await secureUploadFile(
        file,
        undefined,  // description
        true,       // isPublic
        metadata    // browserMetadata
    );

    return {
        success: result.success,
        photo_id: result.photo_id,
        error: result.error
    };
}

/**
 * Trigger photo upload sync. Prefers Background Sync API (service worker)
 * when available, falls back to foreground upload on the main thread.
 *
 * This is the single entry point — call it from anywhere:
 * - After capturing a photo
 * - After user logs in
 * - After coming back online
 * - Manual retry button
 *
 * Skips silently if user is not authenticated — uploads would fail anyway
 * and we'd needlessly mark photos as 'failed' with retry counts burned.
 *
 * Uses probe-then-fallback: registers background sync, waits 500ms for
 * the SW to report activity via postMessage, then falls back to foreground
 * if the SW is unresponsive (stale cache, crash, etc).
 */
export async function triggerPhotoSync(): Promise<void> {
    const authState = get(auth);
    if (!authState.is_authenticated) {
        console.log(`${LOG_PREFIX} Skipping sync — not authenticated`);
        return;
    }

    const settings = await getSettings();
    if (!settings.auto_upload_enabled) {
        console.log(`${LOG_PREFIX} Skipping sync — auto_upload is disabled`);
        return;
    }

    initSyncStatusListener(); // idempotent

    // Sync processing → completed/failed before starting new uploads
    try {
        await syncProcessingPhotosStatus(mainThreadAuthFetch);
    } catch (error) {
        console.warn(`${LOG_PREFIX} Processing status sync failed:`, error);
    }

    if (isBackgroundSyncSupported()) {
        try {
            const reg = await navigator.serviceWorker.ready;
            await (reg as any).sync.register('photo-upload');
            console.log(`${LOG_PREFIX} Background sync registered, probing SW...`);

            // Wait for SW to respond with a status report
            await new Promise(resolve => setTimeout(resolve, 500));

            if (isSwAlive(1000)) {
                console.log(`${LOG_PREFIX} SW is alive and uploading`);
                return;
            }

            console.warn(`${LOG_PREFIX} SW did not respond, falling back to foreground`);
        } catch (error) {
            console.warn(`${LOG_PREFIX} Background sync failed, falling back to foreground:`, error);
        }
    }

    startForegroundSync();
}

function startForegroundSync(): void {
    console.log(`${LOG_PREFIX} Using foreground upload`);
    const reporter = createFgStatusReporter();
    uploadPendingPhotos(foregroundUploader, {
        source: 'fg',
        reporter,
        authFetch: mainThreadAuthFetch
    }).catch(error => {
        console.error(`${LOG_PREFIX} Foreground upload error:`, error);
    });
}
