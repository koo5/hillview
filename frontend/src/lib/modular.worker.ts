/*
 * Modular Worker Architecture
 *
 * This worker uses focused, single-responsibility modules instead of a monolithic design.
 * Each module handles one specific concern with clear interfaces.
 */

/// <reference lib="webworker" />

import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { MessageQueue } from './MessageQueue';
import { PhotoOperations } from './photoOperations';
import { DEFAULT_RANGE_METERS, MAX_PHOTOS_IN_AREA, MAX_PHOTOS_IN_RANGE } from './photoWorkerConstants';

// Import our new modules
import { MessageRouter, type MessageHandlers } from './worker/MessageRouter';
import { SourcePhotosState, type SourceId } from './worker/SourcePhotosState';
import { ProcessManager } from './worker/ProcessManager';
import { AuthTokenManager } from './worker/AuthTokenManager';
import { FrontendState } from './worker/FrontendState';
import { WorkerEventLoop } from './worker/WorkerEventLoop';
import { PhotoCuller } from './worker/PhotoCuller';

declare const __WORKER_VERSION__: string;
export const WORKER_VERSION = __WORKER_VERSION__;
console.log(`🢄ModularWorker: Worker script loaded with version: ${WORKER_VERSION}`);

// Initialize modules
const messageQueue = new MessageQueue();
const photoOperations = new PhotoOperations();
const processManager = new ProcessManager();
const authTokenManager = new AuthTokenManager((message) => postMessage(message));
const frontendState = new FrontendState(DEFAULT_RANGE_METERS);
const sourcePhotosState = new SourcePhotosState();
const photoCuller = new PhotoCuller();

// Set the max photos configuration
photoOperations.setMaxPhotosInArea(MAX_PHOTOS_IN_AREA);

// Message counter for assigning IDs
let messageIdCounter = 0;

// Photo update function
function sendPhotosUpdate(): void {
    const areaData = frontendState.getAreaData();
    if (!areaData) {
        console.log('ModularWorker: No area data, skipping photo update');
        return;
    }

    // Apply culling to current photos
    const { photos_in_area: photosInArea, photos_in_range: photosInRange } = photoCuller.cullPhotos(
        sourcePhotosState.getPhotosBySource(),
        areaData,
        frontendState.getAreaUpdateId(),
        frontendState.getCurrentRange(),
        MAX_PHOTOS_IN_AREA,
        MAX_PHOTOS_IN_RANGE
    );

    // Send to frontend
    postMessage({
        type: 'photosUpdate',
        photos_in_area: [...photosInArea],
        photos_in_range: [...photosInRange],
        current_range: frontendState.getCurrentRange(),
        timestamp: Date.now()
    });

    console.log(`ModularWorker: Sent ${photosInArea.length} area photos + ${photosInRange.length} range photos`);
}

// Create message handlers that wire everything together
const messageHandlers: MessageHandlers = {
    onFrontendConfigUpdated: (data: { sources: SourceConfig[]; [key: string]: any }, messageId: number) => {
        frontendState.updateConfig(data, messageId);

        // Remove photos from disabled sources when config changes
        sourcePhotosState.removePhotosFromDisabledSources(data.sources);
    },

    onFrontendAreaUpdated: (data: Bounds, messageId: number, range?: number) => {
        frontendState.updateArea(data, messageId, range);
    },

    triggerPhotoCombineProcess: () => {
        // For stream updates - send photos update
        sendPhotosUpdate();
    },

    markProcessAsComplete: (processId: string, processType: string, messageId: number, results?: any) => {
        // Mark the appropriate state as processed
        if (processType === 'config') {
            frontendState.markConfigProcessed(messageId);
        } else if (processType === 'area') {
            frontendState.markAreaProcessed(messageId);
        }

        processManager.cleanupProcess(processId);
        console.log(`ModularWorker: Process ${processId} (${processType}) completed and marked`);
    },

    removeProcessFromTable: (processId: string) => {
        processManager.cleanupProcess(processId);
    },

    updateSourcePhotos: (sourceId: SourceId, photos: PhotoData[]) => {
        sourcePhotosState.setSourcePhotos(sourceId, photos);
        console.log(`ModularWorker: Source ${sourceId} updated with ${photos.length} photos`);
    },

    removePhotoFromState: (photoId: string, source: SourceId) => {
        const removedCount = sourcePhotosState.removePhoto(photoId, source);
        if (removedCount > 0) {
            sendPhotosUpdate();
        }
    },

    removeUserPhotosFromState: (userId: string, source: SourceId) => {
        const removedCount = sourcePhotosState.removeUserPhotos(userId, source);
        if (removedCount > 0) {
            sendPhotosUpdate();
        }
    },

    forwardToast: (message: any) => {
        postMessage(message);
    },

    resolveAuthTokenPromise: (token: string) => {
        authTokenManager.resolveTokenPromise(token);
    },

    cleanupAndShutdown: () => {
        console.log('ModularWorker: Cleaning up all resources');

        // Abort all running processes
        processManager.abortAllProcesses();
        processManager.clearAllProcesses();

        // Clean up photo operations
        photoOperations.cleanup();

        // Clear other state
        sourcePhotosState.clear();
        photoCuller.clearCache();
        authTokenManager.clearPendingPromise();

        // Send confirmation
        postMessage({ type: 'cleanupComplete' });
    }
};

// Create the event loop
const eventLoop = new WorkerEventLoop(
    messageQueue,
    messageHandlers,
    processManager,
    frontendState
);

// Message handler from main thread
function handleMessage(message: any): void {
    // Handle auth token responses
    if (message.type === 'authToken') {
        messageHandlers.resolveAuthTokenPromise(message.token);
        return;
    }

    // Add ID and queue the message
    messageQueue.addMessage({...message, id: messageIdCounter++});
}

// Set up message handler from main thread
self.onmessage = function(e: MessageEvent) {
    handleMessage(e.data);
};

// Start the main loop
eventLoop.start().catch(error => {
    console.error('ModularWorker: Fatal error in main loop:', error);
    postMessage({
        type: 'error',
        error: {
            message: error?.message || 'Unknown error in main loop',
            timestamp: Date.now()
        }
    });
});

console.log('ModularWorker: Initialization complete');

// Export for testing
export { handleMessage };
