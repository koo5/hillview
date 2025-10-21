import {writable, get} from 'svelte/store';
import {removePlaceholder} from './placeholderInjector';
import type {DevicePhotoMetadata} from './types/photoTypes';
import {invoke} from "@tauri-apps/api/core";
import {BaseDirectory, writeFile} from '@tauri-apps/plugin-fs';

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
	imageData: ImageData;
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
		// Start processing loop
		this.processLoop();
		this.log(this.LOG_TAGS.QUEUE_ADD, 'Capture queue manager initialized');
	}

	private log(tag: string, message: string, data?: any): void {
		const timestamp = new Date().toISOString();
		const logMessage = `${this.LOG_PREFIX} [${tag}] ${timestamp} ${message}`;

		if (data) {
			console.log('🢄' + logMessage, data);
		} else {
			console.log('🢄' + logMessage);
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
						const errorInfo = {
							name: error?.name,
							message: error?.message,
							code: error?.code,
							stack: error?.stack
						};
						console.error('🢄Unhandled error in processItem details:', JSON.stringify(errorInfo, null, 2));
						console.error('🢄Unhandled error in processItem:', error);
					});
				}
			}

			// Wait a bit before checking again
			await new Promise(resolve => setTimeout(resolve, 60));
		}
	}

	private async processItem(item: CaptureQueueItem): Promise<void> {
		// Add to processing set
		this.processingSet.add(item.id);
		this.updateStats();

		try {
			// Step 1: Convert ImageData to Canvas and then to Blob
			this.log(this.LOG_TAGS.QUEUE_PROCESS, 'Converting ImageData to file', { itemId: item.id });

			const canvas = new OffscreenCanvas(item.imageData.width, item.imageData.height);
			const context = canvas.getContext('2d');
			if (!context) {
				throw new Error('Failed to get canvas context');
			}

			// Draw image data to canvas
			context.putImageData(item.imageData, 0, 0);

			// Convert canvas to blob
			const blob = await canvas.convertToBlob({
				type: 'image/jpeg',
				quality: 0.95
			});

			// Convert blob to Uint8Array for file writing
			const arrayBuffer = await blob.arrayBuffer();
			const uint8Array = new Uint8Array(arrayBuffer);

			// Step 2: Generate filename using same pattern as before
			const date = new Date(item.timestamp);
			const year = date.getFullYear();
			const month = String(date.getMonth() + 1).padStart(2, '0');
			const day = String(date.getDate()).padStart(2, '0');
			const hours = String(date.getHours()).padStart(2, '0');
			const minutes = String(date.getMinutes()).padStart(2, '0');
			const seconds = String(date.getSeconds()).padStart(2, '0');
			const filename = `${year}-${month}-${day}-${hours}-${minutes}-${seconds}_${item.id}.jpg`;

			// Step 3: Write file to temp directory
			const tempFilePath = `temp_photos/${filename}`;
			await writeFile(tempFilePath, uint8Array, { baseDir: BaseDirectory.Cache });

			this.log(this.LOG_TAGS.QUEUE_PROCESS, 'File written, calling Rust to process', {
				itemId: item.id,
				filename,
				tempFilePath
			});

			// Step 4: Prepare metadata
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

			// Step 5: Call Rust to process photo with EXIF and save
			const devicePhoto = await invoke('save_photo_from_file', {
				photoId: item.id,
				metadata,
				filePath: tempFilePath, // Tauri will resolve this relative to Cache directory
				filename,
				hideFromGallery: false
			}) as DevicePhotoMetadata;

			this.totalProcessed++;
			this.log(this.LOG_TAGS.PHOTO_SAVE, 'Photo processed successfully', {
				itemId: item.id,
				photoId: devicePhoto.id,
				filename: devicePhoto.filename,
				placeholderReplaced: item.placeholderId,
				totalProcessed: this.totalProcessed
			});

			// PLACEHOLDER SHOULD STAY VISIBLE until device source toggle
			// The placeholder will be removed when device source toggle
			// triggers Kotlin worker to return the real device photo
			// removePlaceholder(item.placeholderId);

		} catch (error) {
			this.totalFailed++;
			this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to process queued photo', {
				itemId: item.id,
				placeholderId: item.placeholderId,
				error: error instanceof Error ? error.message : String(error),
				totalFailed: this.totalFailed
			});

			// Remove placeholder on error
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
