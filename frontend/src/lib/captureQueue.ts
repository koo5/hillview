import {writable, get} from 'svelte/store';
import {removePlaceholder} from './placeholderInjector';
import type {DevicePhotoMetadata} from './types/photoTypes';

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
	location: CaptureLocation;
	timestamp: number;
	mode: 'slow' | 'fast';
	placeholderId: string;
	canvas: OffscreenCanvas;
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
	private readonly LOG_PREFIX = '[CQ]';
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
		// Initialize worker
		this.initWorker();
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
			await new Promise(resolve => setTimeout(resolve, 60));
		}
	}

	private worker!: Worker;

	private async processItem(item: CaptureQueueItem): Promise<void> {
		// Add to processing set
		this.processingSet.add(item.id);
		this.updateStats();

		// Send canvas to worker with transferable object
		this.worker.postMessage(item, [item.canvas]);
	}

	private initWorker(): void {
		this.worker = new Worker('/captureWorker.js', { type: 'module' });

		this.worker.onmessage = (event) => {
			const { type, itemId, placeholderId, devicePhoto, error } = event.data;

			if (type === 'photoSaved') {
				this.totalProcessed++;
				this.log(this.LOG_TAGS.PHOTO_SAVE, 'Photo processed successfully', {
					itemId,
					photoId: devicePhoto.id,
					filename: devicePhoto.filename,
					placeholderReplaced: placeholderId,
					totalProcessed: this.totalProcessed
				});

				// TODO: Handle successful photo save
				// For now, just remove placeholder
				removePlaceholder(placeholderId);

			} else if (type === 'error') {
				this.totalFailed++;
				this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to process queued photo', {
					itemId,
					placeholderId,
					error,
					totalFailed: this.totalFailed
				});

				// Remove placeholder on error
				removePlaceholder(placeholderId);
			}

			// Remove from processing set
			this.processingSet.delete(itemId);
			this.updateStats();
		};

		this.worker.onerror = (error) => {
			this.log(this.LOG_TAGS.PHOTO_ERROR, 'Worker error', error);
		};
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
