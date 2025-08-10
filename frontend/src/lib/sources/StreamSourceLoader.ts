/**
 * Stream Source Loader - Loads photos from streaming endpoints
 * Uses EventSource for real-time photo streaming with bounds-based filtering
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';

export class StreamSourceLoader extends BasePhotoSourceLoader {
    private eventSource?: EventSource;
    private streamPhotos: PhotoData[] = [];
    private completionPromise?: Promise<void>;
    private completionResolve?: () => void;

    constructor(source: any, callbacks: PhotoSourceCallbacks) {
        super(source, callbacks);
    }

    async start(bounds?: Bounds): Promise<void> {
        if (!bounds) {
            // Stream sources without bounds are valid during config setup
            // They will be started with bounds later when area is updated
            console.log(`StreamSourceLoader: Started ${this.source.id} without bounds - waiting for area update`);
            this.isComplete = true;
            return;
        }

        if (!this.source.url) {
            throw new Error('Stream source missing URL');
        }

        console.log(`StreamSourceLoader: Starting stream from ${this.source.url}`);

        // Build URL with bounds parameters
        const url = new URL(this.source.url);
        url.searchParams.set('top_left_lat', bounds.top_left.lat.toString());
        url.searchParams.set('top_left_lng', bounds.top_left.lng.toString());
        url.searchParams.set('bottom_right_lat', bounds.bottom_right.lat.toString());
        url.searchParams.set('bottom_right_lng', bounds.bottom_right.lng.toString());

        // Add any additional parameters
        if (this.source.clientId) {
            url.searchParams.set('client_id', this.source.clientId);
        }

        // Create completion promise
        this.completionPromise = new Promise<void>((resolve) => {
            this.completionResolve = resolve;
            console.log(`StreamSourceLoader: Created completion promise for ${this.source.id}`);
        });

        this.eventSource = new EventSource(url.toString());

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamMessage(data);
            } catch (error) {
                console.error('StreamSourceLoader: Error parsing stream message:', error);
                this.callbacks.onError?.(new Error('Error parsing stream data'));
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('StreamSourceLoader: Stream error:', error);
            this.callbacks.onError?.(new Error('Stream connection error'));
        };

        this.eventSource.onopen = () => {
            console.log('StreamSourceLoader: Stream opened');
        };

        // Return the completion promise
        console.log(`StreamSourceLoader: Returning completion promise for ${this.source.id}`);
        return this.completionPromise;
    }

    private handleStreamMessage(data: any): void {
        switch (data.type) {
            case 'cached_photos':
            case 'live_photos_batch':
                if (data.photos && Array.isArray(data.photos)) {
                    console.log(`StreamSourceLoader: Received ${data.photos.length} photos`);
                    
                    const convertedPhotos: PhotoData[] = data.photos.map((photo: any) => ({
                        id: photo.id,
                        coord: photo.geometry ? 
                            { lat: photo.geometry.coordinates[1], lng: photo.geometry.coordinates[0] } :
                            photo.coord,
                        bearing: photo.computed_compass_angle || photo.compass_angle || photo.bearing || 0,
                        url: photo.thumb_1024_url || photo.url || '',
                        file: photo.file || `stream_${photo.id}`,
                        source_type: this.source.type,
                        source: this.source,
                        altitude: photo.computed_altitude || photo.altitude || 0,
                        captured_at: photo.captured_at,
                        is_pano: photo.is_pano,
                        sizes: photo.sizes || (photo.thumb_1024_url ? {
                            1024: {
                                url: photo.thumb_1024_url,
                                width: 1024,
                                height: 768
                            }
                        } : undefined)
                    }));

                    this.streamPhotos.push(...convertedPhotos);
                    
                    // Send message to worker queue for each batch
                    this.callbacks.enqueueMessage({
                        type: 'photosAdded',
                        sourceId: this.source.id,
                        photos: this.streamPhotos, // Send accumulated photos (growing list)
                        batchType: data.type,
                        region: data.region,
                        hasNext: !!data.next // Track if stream indicates more photos available
                    });
                }
                break;

            case 'stream_complete':
                console.log(`StreamSourceLoader: Stream complete for ${this.source.id}`);
                this.isComplete = true;
                const duration = Date.now() - this.startTime;
                
                // Send completion message to worker queue
                this.callbacks.enqueueMessage({
                    type: 'streamComplete',
                    sourceId: this.source.id,
                    totalPhotos: this.streamPhotos.length,
                    duration
                });

                // Resolve the completion promise
                console.log(`StreamSourceLoader: About to resolve completion promise for ${this.source.id}, resolve function exists: ${!!this.completionResolve}`);
                if (this.completionResolve) {
                    this.completionResolve();
                    console.log(`StreamSourceLoader: Resolved completion promise for ${this.source.id}`);
                }
                break;

            case 'error':
                console.error('StreamSourceLoader: Stream error:', data.message);
                this.callbacks.onError?.(new Error(data.message || 'Unknown stream error'));
                // Resolve the completion promise even on error
                if (this.completionResolve) {
                    this.completionResolve();
                }
                break;

            default:
                console.warn('StreamSourceLoader: Unknown stream message type:', data.type);
        }
    }

    cancel(): void {
        console.log(`StreamSourceLoader: Cancelling stream for ${this.source.id}`);
        super.cancel();
        
        if (this.eventSource) {
            this.eventSource.close();
        }
    }

    getAllPhotos(): PhotoData[] {
        return [...this.streamPhotos];
    }

    getFilteredPhotos(bounds: Bounds): PhotoData[] {
        // Stream sources handle bounds filtering server-side
        return [...this.streamPhotos];
    }

    protected getLoaderType(): string {
        return 'StreamSourceLoader';
    }
}