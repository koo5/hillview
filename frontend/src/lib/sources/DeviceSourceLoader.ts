/**
 * Device Source Loader - Loads photos from local device storage
 * Handles local photo files and metadata
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import type { PhotoSourceOptions } from './PhotoSourceFactory';
import { filterPhotosByArea } from '../workerUtils';
import { invoke } from '@tauri-apps/api/core';

// Device photo format from Android
interface DevicePhoto {
    id: string;
    file_path: string;
    file_name: string;
    file_hash: string;
    file_size: number;
    captured_at: number;
    created_at: number;
    latitude: number;
    longitude: number;
    altitude: number;
    bearing: number;
    accuracy: number; // GPS positioning accuracy in meters
    width: number;
    height: number;
    upload_status: string;
    uploaded_at?: number;
}

interface DevicePhotosResponse {
    photos: DevicePhoto[];
    last_updated: number;
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
    has_more: boolean;
    error?: string;
}

export class DeviceSourceLoader extends BasePhotoSourceLoader {
    private photos: PhotoData[] = [];
    private maxPhotos?: number;

    constructor(source: any, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions) {
        super(source, callbacks);
        this.maxPhotos = options?.maxPhotos;
    }

    async start(bounds?: Bounds): Promise<void> {
        console.log(`🢄DeviceSourceLoader: Loading device photos from ${this.source.path || 'default location'}`);
        console.log(`🢄DeviceSourceLoader: Source config:`, this.source);
        console.log(`🢄DeviceSourceLoader: Bounds:`, bounds);
        console.log(`🢄DeviceSourceLoader: MaxPhotos:`, this.maxPhotos);

        try {
            const requestParams = {
                page: 1,
                page_size: this.maxPhotos || 50,
                minLat: bounds?.top_left.lat,
                maxLat: bounds?.bottom_right.lat,
                minLng: bounds?.top_left.lng,
                maxLng: bounds?.bottom_right.lng
            };

            console.log(`🢄DeviceSourceLoader: Calling get_device_photos with params:`, requestParams);

            // Call Tauri command to get device photos
            const response = await invoke<DevicePhotosResponse>('plugin:hillview|get_device_photos', requestParams);

            if (response.error) {
                throw new Error(response.error);
            }

            // Convert device photos to PhotoData format
            this.photos = response.photos.map(devicePhoto => this.convertToPhotoData(devicePhoto));
            this.isComplete = true;

            const duration = Date.now() - this.startTime;

            this.callbacks.enqueueMessage({
                type: 'photosAdded',
                source_id: this.source.id,
                photos: this.photos,
                duration,
                fromCache: false
            });

            console.log(`🢄DeviceSourceLoader: Loaded ${this.photos.length} photos from device source ${this.source.id}`);

        } catch (error) {
            if (!this.isAborted()) {
                console.error(`🢄DeviceSourceLoader: Error loading device photos:`, error);
                this.callbacks.onError?.(error as Error);
            }
            throw error;
        }
    }

    getAllPhotos(): PhotoData[] {
        return [...this.photos];
    }

    getFilteredPhotos(bounds: Bounds): PhotoData[] {
        return filterPhotosByArea(this.photos, bounds);
    }

    private convertToPhotoData(devicePhoto: DevicePhoto): PhotoData {
        return {
            id: devicePhoto.id,
            uid: `${this.source.id}-${devicePhoto.id}`,
            source_type: this.source.type,
            file: devicePhoto.file_name,
            url: `file://${devicePhoto.file_path}`,
            coord: {
                lat: devicePhoto.latitude,
                lng: devicePhoto.longitude
            },
            bearing: devicePhoto.bearing,
            altitude: devicePhoto.altitude,
            source: this.source,
            is_device_photo: true,
            captured_at: devicePhoto.captured_at,
            accuracy: devicePhoto.accuracy,
            file_hash: devicePhoto.file_hash
        };
    }

    protected getLoaderType(): string {
        return 'DeviceSourceLoader';
    }
}
