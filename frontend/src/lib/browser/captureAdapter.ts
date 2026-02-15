// Adapter to connect browser photo capture to storage
// Converts ImageData to Blob and saves to IndexedDB

import { photoStorage, type BrowserPhoto } from './photoStorage';
import type { CaptureQueueItem } from '../captureQueue';

export class BrowserCaptureAdapter {
    private readonly LOG_PREFIX = '🢄[BrowserCapture]';

    async processCapture(item: CaptureQueueItem): Promise<string> {
        console.log(`${this.LOG_PREFIX} Processing capture ${item.id}`);

        // Convert ImageData to Blob
        const blob = await this.imageDataToBlob(item.image_data);

        // Create photo record with all metadata
        const photo: BrowserPhoto = {
            id: item.id,
            blob,
            location: item.location, // Includes lat, lng, heading/bearing, accuracy, sources
            captured_at: item.captured_at,
            orientation_code: item.orientation_code, // Device rotation (1,3,6,8)
            mode: item.mode,
            uploaded: false,
            upload_attempts: 0,
            created_at: Date.now()
        };

        // Save to IndexedDB
        await photoStorage.save(photo);

        console.log(`${this.LOG_PREFIX} Saved photo ${item.id}`, {
            size: blob.size,
            bearing: item.location.bearing,
            orientation: item.orientation_code,
            mode: item.mode
        });

        return item.id;
    }

    private async imageDataToBlob(imageData: ImageData): Promise<Blob> {
        // Try OffscreenCanvas first (better performance)
        if (typeof OffscreenCanvas !== 'undefined') {
            const canvas = new OffscreenCanvas(imageData.width, imageData.height);
            const ctx = canvas.getContext('2d');
            if (!ctx) throw new Error('Failed to get canvas context');

            ctx.putImageData(imageData, 0, 0);

            return await canvas.convertToBlob({
                type: 'image/jpeg',
                quality: 0.95
            });
        }

        // Fallback to regular canvas
        const canvas = document.createElement('canvas');
        canvas.width = imageData.width;
        canvas.height = imageData.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('Failed to get canvas context');

        ctx.putImageData(imageData, 0, 0);

        return new Promise<Blob>((resolve, reject) => {
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
}

export const browserCaptureAdapter = new BrowserCaptureAdapter();