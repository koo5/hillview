import { writable, get } from 'svelte/store';
import { photoCaptureService, type DevicePhotoMetadata } from './photoCapture';
import { devicePhotos } from './stores';
import { removePlaceholder } from './placeholderInjector';

export interface CaptureLocation {
    latitude: number;
    longitude: number;
    altitude?: number | null;
    accuracy: number;
    heading?: number | null;
    locationSource: 'gps' | 'map';
    bearingSource: string;
}

export interface CaptureQueueItem {
    id: string;
    blob: Blob;
    location: CaptureLocation;
    timestamp: number;
    mode: 'slow' | 'fast';
    placeholderId: string;
}

export interface QueueStats {
    size: number;
    processing: boolean;
    processingCount: number;
    slowModeCount: number;
    fastModeCount: number;
    totalCaptured: number;
    totalProcessed: number;
    totalFailed: number;
}

class CaptureQueueManager {
    private queue: CaptureQueueItem[] = [];
    private processingSet = new Set<string>(); // Track items being processed
    private maxQueueSize = 50; // Default, can be configured
    private maxConcurrency = 3; // Maximum parallel processing tasks
    private slowModeCount = 0;
    private fastModeCount = 0;
    private totalProcessed = 0;
    private totalFailed = 0;

    // Logging constants for greppability
    private readonly LOG_PREFIX = '[CAPTURE_QUEUE]';
    private readonly LOG_TAGS = {
        QUEUE_ADD: 'QUEUE_ADD',
        QUEUE_FULL: 'QUEUE_FULL',
        QUEUE_PROCESS: 'QUEUE_PROCESS',
        PHOTO_SAVE: 'PHOTO_SAVE',
        PHOTO_ERROR: 'PHOTO_ERROR',
        STATS_UPDATE: 'STATS_UPDATE',
        CONCURRENCY: 'CONCURRENCY'
    };

    // Store for queue statistics
    public stats = writable<QueueStats>({
        size: 0,
        processing: false,
        processingCount: 0,
        slowModeCount: 0,
        fastModeCount: 0,
        totalCaptured: 0,
        totalProcessed: 0,
        totalFailed: 0
    });

    constructor() {
        // Start processing loop
        this.processLoop();
        this.log(this.LOG_TAGS.QUEUE_ADD, 'Capture queue manager initialized');
    }

    private log(tag: string, message: string, data?: any): void {
        const timestamp = new Date().toISOString();
        const logMessage = `${this.LOG_PREFIX} [${tag}] ${timestamp} ${message}`;

        if (data) {
            console.log(logMessage, data);
        } else {
            console.log(logMessage);
        }
    }

    setMaxQueueSize(size: number): void {
        this.maxQueueSize = size;
    }

    setMaxConcurrency(concurrency: number): void {
        this.maxConcurrency = Math.max(1, concurrency);
        this.log(this.LOG_TAGS.CONCURRENCY, `Max concurrency set to ${this.maxConcurrency}`);
    }

    async add(item: CaptureQueueItem): Promise<boolean> {
        // Check queue size limit
        while (this.queue.length >= this.maxQueueSize) {
            this.log(this.LOG_TAGS.QUEUE_FULL, 'Capture queue full', {
                maxSize: this.maxQueueSize,
                currentSize: this.queue.length,
                droppedItemId: this.queue[0]?.id
            });
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        this.queue.push(item);

        // Update counters
        if (item.mode === 'slow') {
            this.slowModeCount++;
        } else {
            this.fastModeCount++;
        }

        this.log(this.LOG_TAGS.QUEUE_ADD, 'Photo added to capture queue', {
            itemId: item.id,
            mode: item.mode,
            queueSize: this.queue.length,
            placeholderId: item.placeholderId
        });

        this.updateStats();
        return true;
    }

    private async processLoop(): Promise<void> {
        while (true) {
            // Process multiple items up to concurrency limit
            while (this.queue.length > 0 && this.processingSet.size < this.maxConcurrency) {
                const item = this.queue.shift();
                if (item) {
                    // Start processing without awaiting (parallel execution)
                    this.processItem(item).catch(error => {
                        console.error('Unhandled error in processItem:', error);
                    });
                }
            }

            // Wait a bit before checking again
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }

    private async processItem(item: CaptureQueueItem): Promise<void> {
        // Add to processing set
        this.processingSet.add(item.id);
        this.updateStats();

        this.log(this.LOG_TAGS.QUEUE_PROCESS, 'Processing queued photo', {
            itemId: item.id,
            mode: item.mode,
            placeholderId: item.placeholderId,
            timestamp: item.timestamp,
            concurrentTasks: this.processingSet.size
        });

        try {
            // Convert blob to File
            const file = new File([item.blob], `photo_${item.timestamp}.jpg`, { type: 'image/jpeg' });

            // Prepare photo data
            const photoData = {
                image: file,
                location: {
                    latitude: item.location.latitude,
                    longitude: item.location.longitude,
                    altitude: item.location.altitude,
                    accuracy: item.location.accuracy
                },
                bearing: item.location.heading,
                timestamp: item.timestamp,
                locationSource: item.location.locationSource,
                bearingSource: item.location.bearingSource
            };

            // Save photo with EXIF
            const savedPhoto = await photoCaptureService.savePhotoWithExif(photoData);

            // Replace placeholder with real photo
            devicePhotos.update(photos => {
                const filtered = photos.filter(p => p.id !== item.placeholderId);
                return [...filtered, savedPhoto];
            });

            // Remove from placeholder store
            removePlaceholder(item.placeholderId);

            this.totalProcessed++;
            this.log(this.LOG_TAGS.PHOTO_SAVE, 'Photo processed successfully', {
                itemId: item.id,
                mode: item.mode,
                savedPhotoId: savedPhoto.id,
                filename: savedPhoto.filename,
                placeholderReplaced: item.placeholderId,
                totalProcessed: this.totalProcessed
            });
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);

            this.totalFailed++;
            this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to process queued photo', JSON.stringify({
                itemId: item.id,
                mode: item.mode,
                placeholderId: item.placeholderId,
                error: errorMessage,
                totalFailed: this.totalFailed
            }));

            // Remove placeholder on error
            devicePhotos.update(photos => photos.filter(p => p.id !== item.placeholderId));
            removePlaceholder(item.placeholderId);
        } finally {
            // Remove from processing set
            this.processingSet.delete(item.id);
            this.updateStats();
        }
    }

    private updateStats(): void {
        this.stats.set({
            size: this.queue.length,
            processing: this.processingSet.size > 0,
            processingCount: this.processingSet.size,
            slowModeCount: this.slowModeCount,
            fastModeCount: this.fastModeCount,
            totalCaptured: this.slowModeCount + this.fastModeCount,
            totalProcessed: this.totalProcessed,
            totalFailed: this.totalFailed
        });
    }

    reset(): void {
        this.queue = [];
        this.processingSet.clear();
        this.slowModeCount = 0;
        this.fastModeCount = 0;
        this.totalProcessed = 0;
        this.totalFailed = 0;
        this.updateStats();
    }
}

export const captureQueue = new CaptureQueueManager();
