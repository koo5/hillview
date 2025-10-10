/**
 * Kotlin Photo Worker - Tauri integration adapter for Kotlin photo processing
 *
 * Provides the same interface as the Web Worker but uses the Kotlin PhotoWorkerService
 * via Tauri commands. Solves the "window is not defined" issue by moving photo
 * processing to the native Kotlin layer.
 */

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { get } from 'svelte/store';
import { spatialState } from './mapState';

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
    private activeProcesses = new Set<string>();
    private currentRange = 1000; // Default range in meters
    private currentCenter: { lat: number; lng: number } | null = null;
    private lastConfigSources: any[] = [];
    private eventUnlisteners: UnlistenFn[] = [];

    constructor() {
        console.log('🢄KotlinPhotoWorker: Initialized Kotlin photo worker adapter');
    }

    async initialize(): Promise<void> {
        if (this.isInitialized) return;

        console.log('🢄KotlinPhotoWorker: Initializing Kotlin photo worker service');

        // Set up Tauri event listeners for async photo updates from Kotlin
        try {
            const photoUpdateUnlisten = await listen('photo-worker-update', (event) => {
                console.log('🢄KotlinPhotoWorker: Received photo-worker-update event:', event.payload);
                this.handleTauriPhotoUpdate(event.payload as any);
            });
            this.eventUnlisteners.push(photoUpdateUnlisten);

            console.log('🢄KotlinPhotoWorker: Event listeners set up successfully');
        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Failed to set up event listeners:', error);
        }

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

        console.log(`🢄KotlinPhotoWorker: Processing message type: ${message.type}, data:`, message.data);

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

                // Store config for follow-up area update
                this.lastConfigSources = message.data?.config?.sources || [];
                break;

            case 'areaUpdated':
                messageType = 'PROCESS_AREA';
                // Extract sources from current config if available
                const sources = this.extractSourcesFromLastConfig(message.data);

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
                        sources: sources,
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

        // Track active process
        this.activeProcesses.add(processId);

        // Send to Kotlin service
        this.processMessage(workerMessage, message.frontendMessageId)
            .catch(error => {
                console.error('🢄KotlinPhotoWorker: Error processing message:', error);
                this.activeProcesses.delete(processId);
            });
    }

    private lastConfigData: any = null;

    private extractSourcesFromLastConfig(data: any): any[] {
        // Try to extract sources from the message data or use last known sources
        if (data?.config?.sources) {
            this.lastConfigData = data.config;
            return data.config.sources;
        }
        // If no config in this message, use last stored sources (most common case for area updates)
        if (this.lastConfigSources && this.lastConfigSources.length > 0) {
            console.log(`🢄KotlinPhotoWorker: Using stored config sources (${this.lastConfigSources.length} sources)`);
            return this.lastConfigSources;
        }
        // Fallback to lastConfigData if available
        if (this.lastConfigData?.sources) {
            return this.lastConfigData.sources;
        }
        console.warn('🢄KotlinPhotoWorker: No sources available for area update - returning empty array');
        return [];
    }

    private async processMessage(workerMessage: WorkerMessage, frontendMessageId: string): Promise<void> {
        try {
            // Validate message structure
            this.validateWorkerMessage(workerMessage);

            console.log(`🢄KotlinPhotoWorker: Sending message to Kotlin service: ${workerMessage.type} (${workerMessage.processId})`);
            console.log(`🢄KotlinPhotoWorker: Message data before validation:`, JSON.parse(workerMessage.data));

            const messageJson = JSON.stringify(workerMessage);
            console.log(`🢄KotlinPhotoWorker: Serialized message JSON (${messageJson.length} chars):`, messageJson);

            const invokeArgs = { messageJson: messageJson };
            console.log(`🢄KotlinPhotoWorker: Invoke args:`, invokeArgs);

            // Try direct parameter assignment like other commands
            const response = await invoke<ProcessResponse>('plugin:hillview|photo_worker_process', {
                messageJson: messageJson,
                message_json: messageJson  // Also try snake_case
            });

            if (!response.success) {
                throw new Error(response.error || 'Kotlin service returned error');
            }

            // Like new.worker.ts: just acknowledgment, actual results come via events
            console.log('🢄KotlinPhotoWorker: Kotlin service acknowledged message, waiting for async events...');

            // Remove from active processes when complete
            this.activeProcesses.delete(workerMessage.processId);

        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Error in processMessage:', error);
            this.activeProcesses.delete(workerMessage.processId);

            // Send error to frontend
            if (this.onMessageCallback) {
                this.onMessageCallback({
                    type: 'error',
                    error: error instanceof Error ? error.message : 'Unknown error',
                    frontendMessageId
                });
            }
        }
    }

    /**
     * Handle Tauri photo update events from Kotlin PhotoWorkerService
     * This is the async event handler like new.worker.ts onmessage
     */
    private handleTauriPhotoUpdate(eventData: any): void {
        if (!eventData || eventData.type !== 'photosUpdate') {
            console.warn('🢄KotlinPhotoWorker: Invalid or unknown Tauri event data:', eventData);
            return;
        }

        try {
            // Parse the photos from the event data
            const photosInArea = JSON.parse(eventData.photosInArea || '[]');
            const photosInRange = JSON.parse(eventData.photosInRange || '[]');
            const currentRange = eventData.currentRange || this.currentRange;

            console.log(`🢄KotlinPhotoWorker: Received async photos update via Tauri event: ${photosInArea.length} in area, ${photosInRange.length} in range`);

            // Apply range filtering to ensure consistency
            const rangePhotos = this.applyRangeFiltering(photosInArea);

            // Send photos update to frontend (matching Web Worker interface)
            if (this.onMessageCallback) {
                this.onMessageCallback({
                    type: 'photosUpdate',
                    photosInArea: photosInArea,
                    photosInRange: rangePhotos,
                    currentRange: currentRange,
                    timestamp: eventData.timestamp
                });

                // Handle device photo cleanup if applicable
                const devicePhotos = photosInArea.filter((photo: any) =>
                    photo.isDevicePhoto || photo.source_type === 'device'
                );
                if (devicePhotos.length > 0) {
                    const devicePhotoIds = devicePhotos.map((photo: any) => photo.id);
                    this.onMessageCallback({
                        type: 'cleanupPlaceholders',
                        devicePhotoIds
                    });
                }

                // Trigger area update after config for streaming sources
                // This happens after every photos update to maintain sync
                if (photosInArea.length > 0) {
                    console.log('🔧 KOTLIN FIX: Photos received - checking if area update needed for streaming sources');
                    this.triggerAreaUpdateAfterConfig();
                }
            }
        } catch (error) {
            console.error('🢄KotlinPhotoWorker: Error processing Tauri photo update event:', error);
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

        // Cleanup event listeners
        for (const unlisten of this.eventUnlisteners) {
            try {
                unlisten();
            } catch (error) {
                console.warn('🢄KotlinPhotoWorker: Error cleaning up event listener:', error);
            }
        }
        this.eventUnlisteners = [];

        // Abort all active processes
        for (const processId of this.activeProcesses) {
            this.abortProcess(processId);
        }

        this.activeProcesses.clear();
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

    // Get active process count for debugging
    getActiveProcessCount(): number {
        return this.activeProcesses.size;
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