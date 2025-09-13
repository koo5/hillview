/*
import { get } from 'svelte/store';
import { client_id } from './data.svelte';
import {backendUrl} from "$lib/config";

export interface MapillaryPhoto {
    id: string;
    geometry: {
        type: 'Point';
        coordinates: [number, number];
    };
    compass_angle?: number;
    computed_compass_angle?: number;
    computed_rotation?: number;
    computed_altitude?: number;
    captured_at?: string;
    is_pano?: boolean;
    thumb_1024_url?: string;
}

export interface StreamMessage {
    type: 'cached_photos' | 'cache_status' | 'live_photos_batch' | 'region_complete' | 'stream_complete' | 'error';
    photos?: MapillaryPhoto[];
    count?: number;
    uncached_regions?: number;
    region?: string;
    photos_count?: number;
    total_live_photos?: number;
    message?: string;
}

export interface MapillaryStreamCallbacks {
    onCachedPhotos?: (photos: MapillaryPhoto[]) => void;
    onCacheStatus?: (uncachedRegions: number) => void;
    onLivePhotosBatch?: (photos: MapillaryPhoto[], region: string) => void;
    onRegionComplete?: (region: string, photosCount: number) => void;
    onStreamComplete?: (totalLivePhotos: number) => void;
    onError?: (message: string) => void;
}

export class MapillaryStreamService {
    private eventSource: EventSource | null = null;
    private callbacks: MapillaryStreamCallbacks = {};
    private isStreaming = false;
    private cleanupTimeout: number | null = null;

    constructor(callbacks: MapillaryStreamCallbacks) {
        this.callbacks = callbacks;
    }

    async startStream(
        topLeftLat: number,
        topLeftLon: number,
        bottomRightLat: number,
        bottomRightLon: number
    ): Promise<void> {
        if (this.isStreaming) {
            this.stopStream();
        }

        const clientId = get(client_id);

        const url = `${backendUrl}/mapillary` +
            `?top_left_lat=${topLeftLat}` +
            `&top_left_lon=${topLeftLon}` +
            `&bottom_right_lat=${bottomRightLat}` +
            `&bottom_right_lon=${bottomRightLon}` +
            `&client_id=${clientId}`;

        this.eventSource = new EventSource(url);
        this.isStreaming = true;

        this.eventSource.onmessage = (event) => {
            try {
                const data: StreamMessage = JSON.parse(event.data);
                this.handleStreamMessage(data);
            } catch (error) {
                console.error('🢄Error parsing stream message:', error);
                this.callbacks.onError?.('Error parsing stream data');
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('🢄Stream error:', error);
            this.callbacks.onError?.('Stream connection error');
            this.stopStream();
        };

        this.eventSource.onopen = () => {
            console.log('🢄Stream opened');
        };
    }

    private handleStreamMessage(data: StreamMessage): void {
        switch (data.type) {
            case 'cached_photos':
                if (data.photos) {
                    this.callbacks.onCachedPhotos?.(data.photos);
                }
                break;

            case 'cache_status':
                if (data.uncached_regions !== undefined) {
                    this.callbacks.onCacheStatus?.(data.uncached_regions);
                }
                break;

            case 'live_photos_batch':
                if (data.photos && data.region) {
                    this.callbacks.onLivePhotosBatch?.(data.photos, data.region);
                }
                break;

            case 'region_complete':
                if (data.region && data.photos_count !== undefined) {
                    this.callbacks.onRegionComplete?.(data.region, data.photos_count);
                }
                break;

            case 'stream_complete':
                if (data.total_live_photos !== undefined) {
                    this.callbacks.onStreamComplete?.(data.total_live_photos);
                }
                this.stopStream();
                break;

            case 'error':
                if (data.message) {
                    this.callbacks.onError?.(data.message);
                }
                break;

            default:
                console.warn('🢄Unknown stream message type:', data.type);
        }
    }

    stopStream(): void {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isStreaming = false;

        // Clear any pending cleanup timeouts
        if (this.cleanupTimeout) {
            clearTimeout(this.cleanupTimeout);
            this.cleanupTimeout = null;
        }
    }

    private cleanup(): void {
        this.stopStream();
    }

    getIsStreaming(): boolean {
        return this.isStreaming;
    }
}

export function createMapillaryStreamService(callbacks: MapillaryStreamCallbacks): MapillaryStreamService {
    return new MapillaryStreamService(callbacks);
}
*/
