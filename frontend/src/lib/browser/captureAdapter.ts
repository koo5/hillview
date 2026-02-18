// Adapter to connect browser photo capture to storage
// Saves ImageData to IndexedDB via browserPhotoStorage

import { browserPhotoStorage } from './photoStorage';
import type { CaptureQueueItem } from '../captureQueue';

export class BrowserCaptureAdapter {
    private readonly LOG_PREFIX = '🢄[BrowserCapture]';

    async processCapture(item: CaptureQueueItem): Promise<string> {
        console.log(`${this.LOG_PREFIX} Processing capture ${item.id}`);

        // Save directly to IndexedDB - browserPhotoStorage handles ImageData to Blob conversion
        await browserPhotoStorage.savePhotoFromImageData(
            item.id,
            item.image_data,
            {
                location: item.location,
                captured_at: item.captured_at,
                orientation_code: item.orientation_code
            }
        );

        console.log(`${this.LOG_PREFIX} Saved photo ${item.id}`, {
            width: item.image_data.width,
            height: item.image_data.height,
            bearing: item.location.bearing,
            orientation: item.orientation_code
        });

        return item.id;
    }
}

export const browserCaptureAdapter = new BrowserCaptureAdapter();