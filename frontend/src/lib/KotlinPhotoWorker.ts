/**
 * Kotlin Photo Worker - Tauri integration adapter for Kotlin photo processing
 *
 * Provides the same interface as the Web Worker but uses the Kotlin PhotoWorkerService
 * via Tauri commands. Solves the "window is not defined" issue by moving photo
 * processing to the native Kotlin layer.
 */

import { invoke } from '@tauri-apps/api/core';
import { get } from 'svelte/store';
import { spatialState } from './mapState';
import { sources } from './data.svelte';
import { kotlinMessageQueue, type QueuedMessage } from './KotlinMessageQueue';

// Kotlin Photo Worker message types
type MessageType = 'PROCESS_CONFIG' | 'PROCESS_AREA' | 'ABORT_PROCESS' | 'CLEANUP';

interface WorkerMessage {
    type: MessageType;
    messageId: number;
    processId: string;
    priority: number;
    data: string; // JSON string
}

interface ProcessResponse {
    success: boolean;
    responseJson?: string;
    error?: string;
}

export class KotlinPhotoWorker {
    private messageIdCounter = 0;
    private processIdCounter = 0;
    private isInitialized = false;
    private onMessageCallback: ((message: any) => void) | null = null;
    private currentRange = 1000; // Default range in meters
    private currentCenter: { lat: number; lng: number } | null = null;

    constructor() {
        console.log('🢄KotlinPhotoWorker: Initialized Kotlin photo worker adapter');
    }

    async initialize(): Promise<void> {
        if (this.isInitialized) return;

        console.log('🢄KotlinPhotoWorker: Initializing Kotlin photo worker service');

        // Set up message handlers using the general message queue
        console.log('🔥 KotlinPhotoWorker: Setting up message handlers...');
        this.setupMessageHandlers();

        // Start the global message polling if not already started
        kotlinMessageQueue.startPolling();

        this.isInitialized = true;
    }

    set onmessage(callback: (event: { data: any }) => void) {
        this.onMessageCallback = callback;
    }

    get onerror() {
        return (error: ErrorEvent) => {
            console.error('🢄KotlinPhotoWorker: Error:', error);
        };
    }

    set onerror(callback: (error: ErrorEvent) => void) {
        // Store error callback if needed
    }

    /**
     * Send message to Kotlin PhotoWorkerService
     * Maps Web Worker interface to Tauri command calls
     */
    postMessage(message: { frontendMessageId: string; type: string; data?: any }): void {
        if (!this.isInitialized) {
            console.error('🢄KotlinPhotoWorker: Worker not initialized');
            return;
        }

        // Convert frontend message to Kotlin worker message format
        const messageId = ++this.messageIdCounter;
        const processId = `process_${++this.processIdCounter}_${Date.now()}`;

        let messageType: MessageType;
        let workerMessage: WorkerMessage;

        console.log(`🢄KotlinPhotoWorker: postMessage: type: ${message.type}, data:`, JSON.stringify(message.data));

        switch (message.type) {
            case 'configUpdated':
                messageType = 'PROCESS_CONFIG';
                workerMessage = {
                    type: messageType,
                    messageId,
                    processId,
                    priority: 1, // High priority for config changes
                    data: JSON.stringify({
                        sources: message.data?.config?.sources || []
                    })
                };
                break;

            case 'areaUpdated':
                messageType = 'PROCESS_AREA';
                // Get current sources from store (frontend context)
                const currentSources = get(sources);

                // Update current range and center for range filtering
                if (message.data?.range) {
                    this.currentRange = message.data.range;
                }
                if (message.data?.area) {
                    // Calculate center of bounds for range filtering
                    const bounds = message.data.area;
                    this.currentCenter = {
                        lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
                        lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
                    };
                }

                workerMessage = {
                    type: messageType,
                    messageId,
                    processId,
                    priority: 2, // Lower priority for area updates
                    data: JSON.stringify({
                        sources: currentSources,
                        bounds: message.data?.area,
                        maxPhotos: 400 // Default max photos
                    })
                };
                break;

            case 'removePhoto':
            case 'removeUserPhotos':
                // These operations don't require Kotlin processing yet
                console.log(`🢄KotlinPhotoWorker: ${message.type} not implemented in Kotlin service yet`);
                return;

            default:
                console.warn('🢄KotlinPhotoWorker: Unknown message type:', message.type);
                return;
        }


        // Send to Kotlin service
        this.processMessage(workerMessage, message.frontendMessageId)
            .catch(error => {
                console.error('🢄KotlinPhotoWorker: Error processing message:', error);
            });
    }


    private async processMessage(workerMessage: WorkerMessage, frontendMessageId: string): Promise<void> {
        try {
            // Validate message structure
            this.validateWorkerMessage(workerMessage);

            //console.log(`🢄KotlinPhotoWorker: Sending message to Kotlin service: ${workerMessage.type} (${workerMessage.processId})`);
            //console.log(`🢄KotlinPhotoWorker: Message data before validation:`, JSON.parse(workerMessage.data));

            const messageJson = JSON.stringify(workerMessage);
            //console.log(`🢄KotlinPhotoWorker: Serialized message JSON (${messageJson.length} chars):`, messageJson);

            const invokeArgs = { messageJson: messageJson };
            //console.log(`🢄KotlinPhotoWorker: Invoke args:`, invokeArgs);

            // Try direct parameter assignment like other commands
            const response = await invoke<ProcessResponse>('plugin:hillview|photo_worker_process', {
                messageJson: messageJson,
                message_json: messageJson  // Also try snake_case
            });

            if (!response.success) {
                throw new Error(response.error || 'Kotlin service returned error');
            }

            // Like new.worker.ts: just acknowledgment, actual results come via events
            //console.log('🢄KotlinPhotoWorker: Kotlin service acknowledged message, waiting for async events...');

        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Error in processMessage:', error);

            // Send error to frontend
            if (this.onMessageCallback) {
                this.onMessageCallback({
                    data: {
                        type: 'error',
                        error: error instanceof Error ? error.message : 'Unknown error',
                        frontendMessageId
                    }
                });
            }
        }
    }

    /**
     * Set up message handlers for photo worker messages
     */
    private setupMessageHandlers(): void {
        kotlinMessageQueue.on('photo-worker-update', (message) => {
            this.handlePhotoUpdate(message.payload);
        });

        kotlinMessageQueue.on('photo-worker-error', (message) => {
            this.handleErrorUpdate(message.payload);
        });
    }

    /**
     * Handle photo update messages from Kotlin PhotoWorkerService
     * This is the async message handler like new.worker.ts onmessage
     */
    private handlePhotoUpdate(payload: any): void {
        if (!payload) {
            console.warn('🢄KotlinPhotoWorker: Invalid or empty message payload:', payload);
            return;
        }

        try {
            // Parse the photos from the payload data
            console.log('🔥 DEBUG: payload structure:', JSON.stringify(payload, null, 2));
            const photosInArea = JSON.parse(payload.photosInArea || '[]');
            const photosInRange = JSON.parse(payload.photosInRange || '[]');
            const timestamp = payload.timestamp;

            console.log(`🢄KotlinPhotoWorker: Received async photos update via Tauri event: ${photosInArea.length} in area, ${photosInRange.length} in range`);
            console.log('🔥 DEBUG: First photo:', photosInArea[0]);

            console.log('🔥 DEBUG: About to call applyRangeFiltering...');
            // Apply range filtering to ensure consistency
            const rangePhotos = this.applyRangeFiltering(photosInArea);
            console.log('🔥 DEBUG: applyRangeFiltering completed, got', rangePhotos.length, 'photos');

            // Send photos update to frontend (matching Web Worker interface)
            console.log('🔥 DEBUG: About to call onMessageCallback...');
            if (this.onMessageCallback) {
                console.log('🔥 DEBUG: Calling onMessageCallback with', photosInArea.length, 'area photos and', rangePhotos.length, 'range photos');
                this.onMessageCallback({
                    data: {
                        type: 'photosUpdate',
                        photosInArea: photosInArea,
                        photosInRange: rangePhotos,
                        timestamp: timestamp
                    }
                });
                console.log('🔥 DEBUG: onMessageCallback completed');

                // Handle device photo cleanup if applicable
                const devicePhotos = photosInArea.filter((photo: any) =>
                    photo.isDevicePhoto || photo.source_type === 'device'
                );
                if (devicePhotos.length > 0) {
                    const devicePhotoIds = devicePhotos.map((photo: any) => photo.id);
                    this.onMessageCallback({
                        data: {
                            type: 'cleanupPlaceholders',
                            devicePhotoIds
                        }
                    });
                }

                // Note: Do NOT trigger area update here - that creates infinite loops!
                // Area updates should only happen from config changes or spatial changes
            }
        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Error processing Tauri photo update event:', error);
        }
    }

    /**
     * Handle error messages from Kotlin PhotoWorkerService
     * This matches the error handling of new.worker.ts
     */
    private handleErrorUpdate(payload: any): void {
        if (!payload) {
            console.warn('🢄KotlinPhotoWorker: Invalid or empty error payload:', payload);
            return;
        }

        try {
            const errorMessage = payload.error || 'Unknown error from Kotlin service';
            const timestamp = payload.timestamp || Date.now();

            console.error(`🢄KotlinPhotoWorker: Received error from Kotlin service: ${errorMessage}`);

            // Send error to frontend using the same format as new.worker.ts
            if (this.onMessageCallback) {
                this.onMessageCallback({
                    data: {
                        type: 'error',
                        error: {
                            message: errorMessage,
                            timestamp: timestamp
                        }
                    }
                });
            }
        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Error processing Tauri error event:', error);
        }
    }

    /**
     * Trigger area update after config processing to ensure streaming sources get current bounds
     * This matches the behavior of simplePhotoWorker.ts lines 263-271
     */
    private async triggerAreaUpdateAfterConfig(): Promise<void> {
        console.log('🢄KotlinPhotoWorker: Triggering area update after config to load streaming sources...');

        const currentSpatial = get(spatialState);
        if (currentSpatial.bounds) {
            console.log('🢄KotlinPhotoWorker: Sending area update after config to trigger streaming sources...');

            // Create area update message with proper frontendMessageId
            const areaMessage = {
                frontendMessageId: `frontend_auto_${++this.messageIdCounter}`,
                type: 'areaUpdated' as const,
                data: {
                    area: currentSpatial.bounds,
                    range: currentSpatial.range
                }
            };

            // Send the area update message
            this.postMessage(areaMessage);
        } else {
            console.log('🢄KotlinPhotoWorker: No bounds available for area update after config');
        }
    }


    terminate(): void {
        console.log('🢄KotlinPhotoWorker: Terminating Kotlin photo worker');

        // Remove message handlers from the global queue
        kotlinMessageQueue.off('photo-worker-update', (message) => {
            this.handlePhotoUpdate(message.payload);
        });
        kotlinMessageQueue.off('photo-worker-error', (message) => {
            this.handleErrorUpdate(message.payload);
        });

        this.isInitialized = false;
        this.onMessageCallback = null;
    }

    private async abortProcess(processId: string): Promise<void> {
        try {
            const abortMessage: WorkerMessage = {
                type: 'ABORT_PROCESS',
                messageId: ++this.messageIdCounter,
                processId,
                priority: 999, // Highest priority
                data: JSON.stringify({})
            };

            const messageJson = JSON.stringify(abortMessage);
            await invoke<ProcessResponse>('plugin:hillview|photo_worker_process', {
                messageJson: messageJson
            });

            console.log(`🢄KotlinPhotoWorker: Aborted process ${processId}`);
        } catch (error) {
            console.error(`🢄KotlinPhotoWorker: Error aborting process ${processId}:`, error);
        }
    }

    // Helper method to check if worker is ready
    isReady(): boolean {
        return this.isInitialized;
    }


    /**
     * Apply range filtering using simple distance calculation
     * This mirrors the AngularRangeCuller functionality but in TypeScript
     */
    private applyRangeFiltering(photos: any[]): any[] {
        if (!this.currentCenter || this.currentRange <= 0) {
            return photos;
        }

        const center = this.currentCenter;
        const maxRange = this.currentRange;

        // Filter photos within range and add distance
        const photosInRange = photos
            .map(photo => {
                const distance = this.calculateDistance(
                    center.lat, center.lng,
                    photo.coord.lat, photo.coord.lng
                );
                return {
                    ...photo,
                    range_distance: distance
                };
            })
            .filter(photo => photo.range_distance <= maxRange)
            .sort((a, b) => a.range_distance - b.range_distance);

        // Limit to maximum range photos (similar to AngularRangeCuller)
        const maxRangePhotos = 200;
        return photosInRange.slice(0, maxRangePhotos);
    }

    /**
     * Calculate distance between two points using Haversine formula
     * Same implementation as AngularRangeCuller.kt
     */
    private calculateDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
        const R = 6371000.0; // Earth's radius in meters

        const φ1 = lat1 * Math.PI / 180;
        const φ2 = lat2 * Math.PI / 180;
        const Δφ = (lat2 - lat1) * Math.PI / 180;
        const Δλ = (lng2 - lng1) * Math.PI / 180;

        const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
                Math.cos(φ1) * Math.cos(φ2) *
                Math.sin(Δλ / 2) * Math.sin(Δλ / 2);

        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

    /**
     * Validate WorkerMessage structure before sending to Kotlin
     */
    private validateWorkerMessage(message: WorkerMessage): void {
        if (!message.type || !['PROCESS_CONFIG', 'PROCESS_AREA', 'ABORT_PROCESS', 'CLEANUP'].includes(message.type)) {
            throw new Error(`Invalid message type: ${message.type}`);
        }

        if (typeof message.messageId !== 'number' || message.messageId <= 0) {
            throw new Error(`Invalid messageId: ${message.messageId}`);
        }

        if (!message.processId || typeof message.processId !== 'string') {
            throw new Error(`Invalid processId: ${message.processId}`);
        }

        if (typeof message.priority !== 'number' || message.priority <= 0) {
            throw new Error(`Invalid priority: ${message.priority}`);
        }

        // Type-specific validation - parse JSON data first
        try {
            const parsedData = JSON.parse(message.data);

            if (message.type === 'PROCESS_AREA') {
                if (!parsedData?.bounds) {
                    throw new Error('PROCESS_AREA message missing bounds data');
                }
                if (!parsedData?.sources || !Array.isArray(parsedData.sources)) {
                    throw new Error('PROCESS_AREA message missing or invalid sources data');
                }
            }

            if (message.type === 'PROCESS_CONFIG') {
                if (!parsedData?.sources || !Array.isArray(parsedData.sources)) {
                    throw new Error('PROCESS_CONFIG message missing or invalid sources data');
                }
            }
        } catch (jsonError) {
            throw new Error(`Invalid JSON in message data: ${jsonError instanceof Error ? jsonError.message : 'Unknown error'}`);
        }
    }
}
