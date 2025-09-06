import { invoke } from '@tauri-apps/api/core';
import { generateUnicodeGuid } from './unicodeGuid';
import { get } from 'svelte/store';
import { photoCaptureSettings } from './stores';

import type {
	PhotoMetadata,
	CapturedPhotoData,
	DevicePhotoMetadata
} from './types/photoTypes';

// Re-export for modules that import from here
export type { DevicePhotoMetadata, CapturedPhotoData, PhotoMetadata };

export interface ProcessedPhoto {
	data: number[];
	metadata: PhotoMetadata;
}

export interface DevicePhotosDb {
	photos: DevicePhotoMetadata[];
	last_updated: number;
}

class PhotoCaptureService {
	// Logging constants for greppability
	private readonly LOG_PREFIX = '[CAPTURE]';
	private readonly LOG_TAGS = {
		SAVE_START: 'SAVE_START',
		SAVE_SUCCESS: 'SAVE_SUCCESS',
		SAVE_ERROR: 'SAVE_ERROR',
		LOAD_START: 'LOAD_START',
		LOAD_SUCCESS: 'LOAD_SUCCESS',
		LOAD_ERROR: 'LOAD_ERROR',
		DELETE_START: 'DELETE_START',
		DELETE_SUCCESS: 'DELETE_SUCCESS',
		DELETE_ERROR: 'DELETE_ERROR'
	};

	private log(tag: string, message: string, data?: any): void {
		const logMessage = `${this.LOG_PREFIX} [${tag}] ${message}`;

		if (data) {
			console.log(logMessage, data);
		} else {
			console.log(logMessage);
		}
	}

	async savePhotoWithExif(photoData: CapturedPhotoData): Promise<DevicePhotoMetadata> {
		// Convert File to array buffer
		const arrayBuffer = await photoData.image.arrayBuffer();
		const uint8Array = new Uint8Array(arrayBuffer);
		const imageData = Array.from(uint8Array);

		// Prepare metadata for Rust
		const metadata: PhotoMetadata = {
			latitude: photoData.location.latitude,
			longitude: photoData.location.longitude,
			altitude: photoData.location.altitude,
			bearing: photoData.bearing,
			timestamp: Math.floor(photoData.timestamp / 1000), // Convert to seconds
			accuracy: photoData.location.accuracy
		};

		// Generate filename with format: 2025-06-30-21-46-00_✨🌟💫🦋🌸🔮.jpg
		const date = new Date(photoData.timestamp);
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const hours = String(date.getHours()).padStart(2, '0');
		const minutes = String(date.getMinutes()).padStart(2, '0');
		const seconds = String(date.getSeconds()).padStart(2, '0');
		const unicodeGuid = generateUnicodeGuid();
		const filename = `${year}-${month}-${day}-${hours}-${minutes}-${seconds}_${unicodeGuid}.jpg`;

		this.log(this.LOG_TAGS.SAVE_START, 'Starting photo save with EXIF', {
			filename,
			latitude: metadata.latitude,
			longitude: metadata.longitude,
			bearing: metadata.bearing,
			timestamp: metadata.timestamp,
			imageSizeBytes: imageData.length
		});

			// Get current settings
			const settings = get(photoCaptureSettings);

			// Call Rust backend to embed EXIF and save
			const devicePhoto = await invoke<DevicePhotoMetadata>('save_photo_with_metadata', {
				imageData,
				metadata,
				filename,
				hideFromGallery: settings.hideFromGallery
			});

			this.log(this.LOG_TAGS.SAVE_SUCCESS, 'Photo saved successfully', JSON.stringify({
				photoId: devicePhoto.id,
				filename: devicePhoto.filename,
				path: devicePhoto.path,
				hideFromGallery: settings.hideFromGallery
			}));

			return devicePhoto;
	}

	async loadDevicePhotos(): Promise<DevicePhotosDb> {
		try {
			return await invoke<DevicePhotosDb>('load_device_photos_db');
		} catch (error) {
			console.debug('🢄Failed to load device photos:', error instanceof Error ? error.message : String(error));
			return { photos: [], last_updated: 0 };
		}
	}

	async loadDirectoryPhotos(directoryPath: string): Promise<DevicePhotosDb> {
		try {
			return await invoke<DevicePhotosDb>('scan_directory_for_photos', { directoryPath });
		} catch (error) {
			console.debug('🢄Failed to load directory photos:', error instanceof Error ? error.message : String(error));
			return { photos: [], last_updated: 0 };
		}
	}

}

export const photoCaptureService = new PhotoCaptureService();
