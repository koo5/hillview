/**
 * Kotlin Photo Worker - Tauri integration adapter for Kotlin photo processing
 *
 * Provides the same interface as the Web Worker but uses the Kotlin PhotoWorkerService
 * via Tauri commands. Solves the "window is not defined" issue by moving photo
 * processing to the native Kotlin layer.
 */

import { invoke } from '@tauri-apps/api/core';

// Kotlin Photo Worker message types
type MessageType = 'PROCESS_CONFIG' | 'PROCESS_AREA' | 'ABORT_PROCESS' | 'CLEANUP';
type ResponseType = 'PROCESS_STARTED' | 'CONFIG_COMPLETE' | 'AREA_COMPLETE' | 'PROCESS_ABORTED' | 'CLEANUP_COMPLETE' | 'ERROR';

interface WorkerMessage {
    type: MessageType;
    messageId: number;
    processId: string;
    priority: number;
    data: string; // JSON string
}

interface WorkerResponse {
    messageId: number;
    type: ResponseType;
    processId: string;
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

    constructor() {
        console.log('🢄KotlinPhotoWorker: Initialized Kotlin photo worker adapter');
    }

    async initialize(): Promise<void> {
        if (this.isInitialized) return;

        console.log('🢄KotlinPhotoWorker: Initializing Kotlin photo worker service');
        this.isInitialized = true;

        // TODO: Set up event listeners for Tauri events from Kotlin service
        // For now, we'll use polling or immediate responses
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
        // If no config in this message, try to use last stored config
        if (this.lastConfigData?.sources) {
            return this.lastConfigData.sources;
        }
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

            if (response.responseJson) {
                try {
                    const workerResponse: WorkerResponse = JSON.parse(response.responseJson);
                    if (workerResponse && typeof workerResponse === 'object' && workerResponse.type) {
                        this.handleKotlinResponse(workerResponse, frontendMessageId);
                    } else {
                        console.error('🢄KotlinPhotoWorker: Invalid response structure:', workerResponse);
                        throw new Error('Invalid response structure from Kotlin service');
                    }
                } catch (parseError) {
                    console.error('🢄KotlinPhotoWorker: Failed to parse response JSON:', response.responseJson);
                    throw new Error(`Failed to parse Kotlin response: ${parseError instanceof Error ? parseError.message : 'Unknown error'}`);
                }
            } else {
                console.log('🢄KotlinPhotoWorker: No response JSON returned from Kotlin service');
            }

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

    private handleKotlinResponse(response: WorkerResponse, frontendMessageId: string): void {
        console.log(`🢄KotlinPhotoWorker: Received response from Kotlin: ${response.type} (${response.processId})`);

        switch (response.type) {
            case 'PROCESS_STARTED':
                // Process started - no immediate action needed
                console.log(`🢄KotlinPhotoWorker: Process ${response.processId} started`);
                break;

            case 'CONFIG_COMPLETE':
                // Config processing complete - photos should be in response.data.photos
                this.handlePhotosUpdate(response, 'config');
                break;

            case 'AREA_COMPLETE':
                // Area processing complete - photos should be in response.data.photos
                this.handlePhotosUpdate(response, 'area');
                break;

            case 'PROCESS_ABORTED':
                console.log(`🢄KotlinPhotoWorker: Process ${response.processId} aborted`);
                break;

            case 'ERROR':
                const errorData = JSON.parse(response.data);
                console.error('🢄KotlinPhotoWorker: Kotlin service error:', errorData.error);
                if (this.onMessageCallback) {
                    this.onMessageCallback({
                        type: 'error',
                        error: errorData.error,
                        frontendMessageId
                    });
                }
                break;

            default:
                console.warn('🢄KotlinPhotoWorker: Unknown response type:', response.type);
        }
    }

    private handlePhotosUpdate(response: WorkerResponse, triggerType: 'config' | 'area'): void {
        const responseData = JSON.parse(response.data);
        const photos = responseData.photos as any[] || [];

        console.log(`🢄KotlinPhotoWorker: Received ${photos.length} photos from ${triggerType} update`);

        // Convert photos to the format expected by the frontend
        const formattedPhotos = photos.map(photo => ({
            ...photo,
            // Ensure all required fields are present
            uid: photo.uid || `${photo.source?.id || 'unknown'}-${photo.id}`,
            isDevicePhoto: photo.isDevicePhoto || photo.source_type === 'device'
        }));

        // Apply range filtering if we have spatial state
        const rangePhotos = this.applyRangeFiltering(formattedPhotos);

        // Send photos update to frontend (matching Web Worker interface)
        if (this.onMessageCallback) {
            this.onMessageCallback({
                type: 'photosUpdate',
                photosInArea: formattedPhotos,
                photosInRange: rangePhotos,
                currentRange: this.currentRange,
                triggerType
            });

            // Handle device photo cleanup if applicable
            const devicePhotos = formattedPhotos.filter(photo => photo.isDevicePhoto);
            if (devicePhotos.length > 0) {
                const devicePhotoIds = devicePhotos.map(photo => photo.id);
                this.onMessageCallback({
                    type: 'cleanupPlaceholders',
                    devicePhotoIds
                });
            }
        }
    }

    terminate(): void {
        console.log('🢄KotlinPhotoWorker: Terminating Kotlin photo worker');

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