// Photo capture worker - processes offscreen canvases
import { invoke } from '@tauri-apps/api/core';
import type { CaptureQueueItem } from '../lib/captureQueue';

const LOG_PREFIX = '🢄[CAPTURE_WORKER]';

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
        const workerStartTime = performance.now();
        log(`TIMING 🕐 WORKER START: ${workerStartTime.toFixed(1)}ms - Processing canvas`, { itemId: item.id });
        log('OffscreenCanvas available:', typeof OffscreenCanvas !== 'undefined');
        log('ImageData size:', JSON.stringify(
			{ width: item.image_data.width, height: item.image_data.height }));

        // Create new offscreen canvas in worker
        if (typeof OffscreenCanvas === 'undefined') {
            throw new Error('OffscreenCanvas not supported in worker');
        }

        const canvasCreateStartTime = performance.now();
        log('Creating OffscreenCanvas...');
        const canvas = new OffscreenCanvas(item.image_data.width, item.image_data.height);
        const canvasCreateEndTime = performance.now();
        log(`TIMING 🖼️ WORKER CANVAS CREATE: ${(canvasCreateEndTime - canvasCreateStartTime).toFixed(1)}ms`);

        const context = canvas.getContext('2d');
        if (!context) {
            throw new Error('Failed to get offscreen canvas context');
        }

        // Draw image data to canvas
        const putDataStartTime = performance.now();
        context.putImageData(item.image_data, 0, 0);
        const putDataEndTime = performance.now();
        log(`TIMING 📊 WORKER PUT IMAGE DATA: ${(putDataEndTime - putDataStartTime).toFixed(1)}ms`);

        // Convert canvas to blob
        const blobStartTime = performance.now();
        const blob = await canvas.convertToBlob({
            type: 'image/jpeg',
            quality: 0.95
        });
        const blobEndTime = performance.now();
        log(`TIMING 🗜️ WORKER CONVERT TO BLOB: ${(blobEndTime - blobStartTime).toFixed(1)}ms`);

        if (!blob) {
            throw new Error('Failed to create blob from canvas');
        }

        log('Canvas converted to blob', JSON.stringify({
            itemId: item.id,
            blobSize: blob.size
        }));

        // Convert blob to array buffer for Rust
        const arrayBufferStartTime = performance.now();
        const arrayBuffer = await blob.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        const imageData = Array.from(uint8Array);
        const arrayBufferEndTime = performance.now();
        log(`TIMING 🔄 WORKER ARRAY BUFFER CONVERSION: ${(arrayBufferEndTime - arrayBufferStartTime).toFixed(1)}ms, size: ${imageData.length} bytes`);

        // Send image data in chunks to keep UI responsive
        const CHUNK_SIZE = 1024*1024;
        const totalChunks = Math.ceil(imageData.length / CHUNK_SIZE);

        log('Sending image data in chunks', {
            itemId: item.id,
            totalBytes: imageData.length,
            totalChunks,
            chunkSize: CHUNK_SIZE
        });

        const chunkingStartTime = performance.now();
        let totalDelayTime = 0;

        // Send chunks with small delays to keep UI responsive
        for (let i = 0; i < totalChunks; i++) {
            const chunkStartTime = performance.now();
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, imageData.length);
            const chunk = imageData.slice(start, end);

            // Convert to transferable Uint8Array for zero-copy transfer
            const chunkBuffer = new Uint8Array(chunk);

            postMessage({
                type: 'photoChunk',
                photoId: item.id,
                chunk: chunkBuffer,
                chunkIndex: i,
                totalChunks,
                isFirstChunk: i === 0,
                isLastChunk: i === totalChunks - 1,
                item: i === totalChunks - 1 ? item : undefined // Only send item with last chunk
            }, [chunkBuffer.buffer]); // Transfer the ArrayBuffer

			await new Promise(resolve => setTimeout(resolve, 30));

			/*
            const chunkEndTime = performance.now();

            // Small delay between chunks to keep UI responsive - reduced from 150ms to 25ms
            if (i < totalChunks - 1) {
                const delayStartTime = performance.now();
                //await new Promise(resolve => setTimeout(resolve, 15));
                const delayEndTime = performance.now();
                totalDelayTime += (delayEndTime - delayStartTime);
                log(`TIMING ⏱️ WORKER CHUNK ${i+1}/${totalChunks}: ${(chunkEndTime - chunkStartTime).toFixed(1)}ms + 25ms delay`);
            } else {
                log(`TIMING 📦 WORKER FINAL CHUNK ${i+1}/${totalChunks}: ${(chunkEndTime - chunkStartTime).toFixed(1)}ms`);
            }*/
        }

        const chunkingEndTime = performance.now();
        const workerEndTime = performance.now();
        log(`TIMING ✅ WORKER COMPLETE: total=${(workerEndTime - workerStartTime).toFixed(1)}ms, chunking=${(chunkingEndTime - chunkingStartTime).toFixed(1)}ms, delays=${totalDelayTime.toFixed(1)}ms`);
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
