import {writable, get} from 'svelte/store';
import {removePlaceholder} from './placeholderInjector';
import type {DevicePhotoMetadata} from './types/photoTypes';
import {invoke} from "@tauri-apps/api/core";
import {frontendBusy} from "$lib/data.svelte";

export interface CaptureLocation {
	latitude: number;
	longitude: number;
	altitude?: number | null;
	accuracy: number;
	heading?: number | null;
	location_source: 'gps' | 'map';
	bearing_source: string;
}

export interface CaptureQueueItem {
	id: string;
	location: CaptureLocation;
	captured_at: number;
	mode: 'slow' | 'fast';
	placeholder_id: string;
	image_data: ImageData;
	orientation_code: number; // EXIF orientation value (1, 3, 6, 8)
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
			placeholder_id: item.placeholder_id
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

	private worker!: Worker;

	private async processItem(item: CaptureQueueItem): Promise<void> {
		// Add to processing set
		this.processingSet.add(item.id);
		this.updateStats();

		try {
			// Check if worker is available
			if (!this.worker) {
				throw new Error('Worker not initialized');
			}

			// Send image data to worker with transfer for better performance
			this.log(this.LOG_TAGS.QUEUE_PROCESS, 'Transferring image data to worker', { itemId: item.id });
			this.worker.postMessage(item, [item.image_data.data.buffer]);
		} catch (error) {
			const errorInfo = {
				name: (error as any)?.name,
				message: (error as any)?.message,
				code: (error as any)?.code,
				stack: (error as any)?.stack
			};
			this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to post message to worker', {
				itemId: item.id,
				errorDetails: errorInfo
			});

			// Remove from processing set on error
			this.processingSet.delete(item.id);
			this.updateStats();
			throw error;
		}
	}

	private initWorker(): void {
		this.worker = new Worker(
			new URL('../workers/captureWorker.ts', import.meta.url),
			{ type: 'module' }
		);

		this.worker.onmessage = async (event) => {
			const { type } = event.data;

			if (type === 'photoChunk') {
				const { photoId, chunk, chunkIndex, totalChunks, isFirstChunk, isLastChunk, item } = event.data;

				try {
					frontendBusy.update(n => n + 1);
					await new Promise(resolve => {requestAnimationFrame(resolve);});

					await invoke('store_photo_chunk', {
						photoId,
						chunk,
						isFirstChunk
					});

					frontendBusy.update(n => n - 1);
					await new Promise(resolve => setTimeout(resolve, 25));

					/*this.log(this.LOG_TAGS.QUEUE_PROCESS, 'Stored photo chunk', {
						photoId,
						chunkIndex,
						totalChunks,
						chunkSize: chunk.length,
						isLastChunk
					});*/

					// If this is the last chunk, save the complete photo
					if (isLastChunk && item) {
						// Prepare metadata
						const metadata = {
							latitude: item.location.latitude,
							longitude: item.location.longitude,
							altitude: item.location.altitude,
							bearing: item.location.heading,
							captured_at: item.captured_at,
							accuracy: item.location.accuracy,
							location_source: item.location.location_source,
							bearing_source: item.location.bearing_source,
							orientation_code: item.orientation_code
						};

						// Generate filename
						const date = new Date(item.captured_at);
						const year = date.getFullYear();
						const month = String(date.getMonth() + 1).padStart(2, '0');
						const day = String(date.getDate()).padStart(2, '0');
						const hours = String(date.getHours()).padStart(2, '0');
						const minutes = String(date.getMinutes()).padStart(2, '0');
						const seconds = String(date.getSeconds()).padStart(2, '0');
						const filename = `${year}-${month}-${day}-${hours}-${minutes}-${seconds}_${item.id}.jpg`;

						this.log(this.LOG_TAGS.QUEUE_PROCESS, 'All chunks sent, saving photo with metadata', JSON.stringify({
							photoId: item.id,
							filename,
							totalChunks
						}));

						// Call Rust to save photo using stored chunks
						const devicePhoto = await invoke('save_photo_with_metadata', {
							photoId: item.id,
							metadata,
							filename,
							hideFromGallery: false
						}) as { id: string; filename: string; [key: string]: any };

						this.totalProcessed++;
						this.log(this.LOG_TAGS.PHOTO_SAVE, 'Photo processed successfully', JSON.stringify({
							itemId: item.id,
							photoId: devicePhoto.id,
							filename: devicePhoto.filename,
							placeholder_replaced: item.placeholder_id,
							totalProcessed: this.totalProcessed
						}));

						// Remove from processing set
						this.processingSet.delete(item.id);
						this.updateStats();
					}
				} catch (error) {
					this.totalFailed++;
					this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to process photo chunk', JSON.stringify({
						photoId,
						chunkIndex,
						error: error instanceof Error ? error.message : String(error),
						totalFailed: this.totalFailed
					}));

					// If this chunk failed and we have the item, clean up
					if (item) {
						removePlaceholder(item.placeholder_id);
						this.processingSet.delete(item.id);
						this.updateStats();
					}
				}

			} else if (type === 'error') {
				const { item, error } = event.data;
				this.totalFailed++;
				this.log(this.LOG_TAGS.PHOTO_ERROR, 'Failed to process queued photo', {
					itemId: item.id,
					placeholder_id: item.placeholder_id,
					error,
					totalFailed: this.totalFailed
				});

				// Remove placeholder on error
				removePlaceholder(item.placeholder_id);

				// Remove from processing set
				this.processingSet.delete(item.id);
				this.updateStats();
			}
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
