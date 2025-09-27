// Photo capture worker - processes offscreen canvases
import { invoke } from '@tauri-apps/api/core';
import type { CaptureQueueItem } from '../lib/captureQueue';

const LOG_PREFIX = '[CAPTURE_WORKER]';

function log(message: string, data?: any): void {
    const timestamp = new Date().toISOString();
    console.log(`${LOG_PREFIX} ${timestamp} ${message}`, data || '');
}

// Queue to hold canvas processing tasks
const canvasQueue: CaptureQueueItem[] = [];
let processing = false;

onmessage = async (event: MessageEvent<CaptureQueueItem>) => {
    const item = event.data;
    log('Received canvas for processing', { itemId: item.id, mode: item.mode });

    // Add to queue
    canvasQueue.push(item);

    // Start processing if not already running
    if (!processing) {
        processQueue();
    }
};

async function processQueue() {
    processing = true;

    while (canvasQueue.length > 0) {
        const item = canvasQueue.shift();
        if (item) {
            await processCanvas(item);
        }
    }

    processing = false;
}

async function processCanvas(item: CaptureQueueItem): Promise<void> {
    try {
        log('Processing canvas', { itemId: item.id });
        log('OffscreenCanvas available:', typeof OffscreenCanvas !== 'undefined');
        log('ImageData size:', { width: item.imageData.width, height: item.imageData.height });

        // Create new offscreen canvas in worker
        if (typeof OffscreenCanvas === 'undefined') {
            throw new Error('OffscreenCanvas not supported in worker');
        }

        log('Creating OffscreenCanvas...');
        const canvas = new OffscreenCanvas(item.imageData.width, item.imageData.height);
        log('OffscreenCanvas created successfully');
        const context = canvas.getContext('2d');
        if (!context) {
            throw new Error('Failed to get offscreen canvas context');
        }

        // Draw image data to canvas
        context.putImageData(item.imageData, 0, 0);

        // Convert canvas to blob
        const blob = await canvas.convertToBlob({
            type: 'image/jpeg',
            quality: 0.95
        });

        if (!blob) {
            throw new Error('Failed to create blob from canvas');
        }

        log('Canvas converted to blob', {
            itemId: item.id,
            blobSize: blob.size
        });

        // Convert blob to array buffer for Rust
        const arrayBuffer = await blob.arrayBuffer();
        const imageData = Array.from(new Uint8Array(arrayBuffer));

        // Prepare metadata
        const metadata = {
            latitude: item.location.latitude,
            longitude: item.location.longitude,
            altitude: item.location.altitude,
            bearing: item.location.heading,
            timestamp: Math.floor(item.timestamp / 1000),
            accuracy: item.location.accuracy,
            locationSource: item.location.locationSource,
            bearingSource: item.location.bearingSource
        };

        // Generate filename
        const date = new Date(item.timestamp);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        const filename = `${year}-${month}-${day}-${hours}-${minutes}-${seconds}_${item.id}.jpg`;

        log('Calling Rust save_photo_with_metadata', {
            itemId: item.id,
            filename,
            imageDataSize: imageData.length
        });

        // Call Rust to save photo
        const devicePhoto = await invoke('save_photo_with_metadata', {
            imageData,
            metadata,
            filename,
            hideFromGallery: false // You might want to pass this from settings
        }) as { id: string; filename: string; [key: string]: any };

        log('Photo saved successfully', {
            itemId: item.id,
            photoId: devicePhoto.id,
            filename: devicePhoto.filename
        });

        // Send success back to main thread
        postMessage({
            type: 'photoSaved',
            itemId: item.id,
            placeholderId: item.placeholderId,
            devicePhoto
        });

    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        log('Error processing canvas', JSON.stringify(errorMessage));

        // Send error back to main thread
        postMessage({
            type: 'error',
            itemId: item.id,
            placeholderId: item.placeholderId,
            error: errorMessage
        });
    }
}
