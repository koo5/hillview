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
        const uint8Array = new Uint8Array(arrayBuffer);
        const imageData = Array.from(uint8Array);

        // Send image data in chunks to keep UI responsive
        const CHUNK_SIZE = 100 * 1024; // 100KB chunks
        const totalChunks = Math.ceil(imageData.length / CHUNK_SIZE);

        log('Sending image data in chunks', {
            itemId: item.id,
            totalBytes: imageData.length,
            totalChunks,
            chunkSize: CHUNK_SIZE
        });

        // Send chunks with small delays to keep UI responsive
        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, imageData.length);
            const chunk = imageData.slice(start, end);

            postMessage({
                type: 'photoChunk',
                photoId: item.id,
                chunk,
                chunkIndex: i,
                totalChunks,
                isFirstChunk: i === 0,
                isLastChunk: i === totalChunks - 1,
                item: i === totalChunks - 1 ? item : undefined // Only send item with last chunk
            });

            // Small delay between chunks to keep UI responsive
            if (i < totalChunks - 1) {
                await new Promise(resolve => setTimeout(resolve, 50));
            }
        }
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : String(error);
		log('Error processing canvas', JSON.stringify(errorMessage));

		// Send error back to main thread
		postMessage({
			type: 'error',
			item,
			error: errorMessage
		});
	}
}
