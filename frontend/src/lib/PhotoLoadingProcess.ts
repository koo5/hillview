import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { filterPhotosByArea } from './workerUtils';

export interface PhotoLoadingCallbacks {
    onProgress?: (loaded: number, total?: number) => void;
    onError?: (error: Error) => void;
    enqueueMessage: (message: any) => void; // Required for integrating with worker message queue
    getCachedJson?: (sourceId: string) => PhotoData[] | undefined; // Get cached JSON data
    setCachedJson?: (sourceId: string, photos: PhotoData[]) => void; // Store cached JSON data
}

export class PhotoLoadingProcess {
    private source: SourceConfig;
    private bounds?: Bounds;
    private abortController?: AbortController;
    private eventSource?: EventSource;
    private startTime: number;
    private isComplete: boolean = false;
    private callbacks: PhotoLoadingCallbacks;
    
    // Data storage
    private streamPhotos: PhotoData[] = []; // For stream sources, accumulate photos

    constructor(source: SourceConfig, callbacks: PhotoLoadingCallbacks) {
        this.source = source;
        this.callbacks = callbacks;
        this.startTime = Date.now();
    }

    async start(bounds?: Bounds): Promise<void> {
        this.bounds = bounds;
        
        try {
            if (this.source.type === 'json') {
                await this.loadJsonSource();
            } else if (this.source.type === 'stream') {
                await this.loadStreamSource();
            } else {
                throw new Error(`Unsupported source type: ${this.source.type}`);
            }
        } catch (error) {
            if (!this.isAborted()) {
                this.callbacks.onError?.(error as Error);
            }
        }
    }

    private async loadJsonSource(): Promise<void> {
        if (!this.source.url) {
            throw new Error('JSON source missing URL');
        }

        // Check if we have cached data from Processors
        const cachedPhotos = this.callbacks.getCachedJson?.(this.source.id);
        if (cachedPhotos) {
            console.log(`PhotoLoadingProcess: JSON source ${this.source.id} using cached data`);
            const duration = Date.now() - this.startTime;
            this.callbacks.enqueueMessage({
                type: 'photosLoaded',
                sourceId: this.source.id,
                photos: cachedPhotos,
                duration,
                fromCache: true
            });
            this.isComplete = true;
            return;
        }

        this.abortController = new AbortController();
        console.log(`PhotoLoadingProcess: Loading JSON from ${this.source.url}`);
        console.log(`PhotoLoadingProcess: Source config:`, JSON.stringify({
            id: this.source.id,
            name: this.source.name,
            type: this.source.type,
            enabled: this.source.enabled,
            url: this.source.url,
            clientId: this.source.clientId
        }));

        const response = await fetch(this.source.url, {
            signal: this.abortController.signal
        });

        console.log(`PhotoLoadingProcess: Response status: ${response.status} ${response.statusText}`);
        console.log(`PhotoLoadingProcess: Response headers:`, Object.fromEntries([...response.headers.entries()]));

        if (!response.ok) {
            console.error(`PhotoLoadingProcess: HTTP error ${response.status} ${response.statusText} for ${this.source.url}`);
            throw new Error(`Failed to fetch from ${this.source.url}: ${response.status} ${response.statusText}`);
        }

        const contentLength = response.headers.get('content-length');
        const total = contentLength ? parseInt(contentLength, 10) : undefined;
        let loaded = 0;

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error('Response body is not readable');
        }

        const chunks: Uint8Array[] = [];

        while (true) {
            this.checkAborted();
            
            const { done, value } = await reader.read();
            if (done) break;

            chunks.push(value);
            loaded += value.length;
            this.callbacks.onProgress?.(loaded, total);
        }

        const decoder = new TextDecoder();
        const jsonText = decoder.decode(new Uint8Array(
            chunks.reduce((acc, chunk) => [...acc, ...chunk], [] as number[])
        ));

        const photos: PhotoData[] = JSON.parse(jsonText);
        
        // Add source reference to each photo
        photos.forEach(photo => {
            photo.source = this.source;
        });

        // Cache the photos in Processors
        this.callbacks.setCachedJson?.(this.source.id, photos);
        this.isComplete = true;

        console.log(`PhotoLoadingProcess: Loaded ${photos.length} photos from JSON source`);

        const duration = Date.now() - this.startTime;
        
        // Send message to worker queue
        this.callbacks.enqueueMessage({
            type: 'photosLoaded',
            sourceId: this.source.id,
            photos: photos,
            duration,
            fromCache: false
        });
    }

    private async loadStreamSource(): Promise<void> {
        if (!this.bounds) {
            throw new Error('Stream source requires bounds');
        }

        if (!this.source.url) {
            throw new Error('Stream source missing URL');
        }

        console.log(`PhotoLoadingProcess: Starting stream from ${this.source.url}`);

        // Build URL with bounds parameters
        const url = new URL(this.source.url);
        url.searchParams.set('top_left_lat', this.bounds.top_left.lat.toString());
        url.searchParams.set('top_left_lng', this.bounds.top_left.lng.toString());
        url.searchParams.set('bottom_right_lat', this.bounds.bottom_right.lat.toString());
        url.searchParams.set('bottom_right_lng', this.bounds.bottom_right.lng.toString());

        // Add any additional parameters
        if (this.source.clientId) {
            url.searchParams.set('client_id', this.source.clientId);
        }

        this.eventSource = new EventSource(url.toString());

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamMessage(data);
            } catch (error) {
                console.error('PhotoLoadingProcess: Error parsing stream message:', error);
                this.callbacks.onError?.(new Error('Error parsing stream data'));
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('PhotoLoadingProcess: Stream error:', error);
            this.callbacks.onError?.(new Error('Stream connection error'));
        };

        this.eventSource.onopen = () => {
            console.log('PhotoLoadingProcess: Stream opened');
        };
    }

    private handleStreamMessage(data: any): void {
        switch (data.type) {
            case 'cached_photos':
            case 'live_photos_batch':
                if (data.photos && Array.isArray(data.photos)) {
                    console.log(`PhotoLoadingProcess: Received ${data.photos.length} photos`);
                    
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
                        photos: convertedPhotos,
                        batchType: data.type,
                        region: data.region
                    });
                }
                break;

            case 'stream_complete':
                console.log('PhotoLoadingProcess: Stream complete');
                this.isComplete = true;
                const duration = Date.now() - this.startTime;
                
                // Send completion message to worker queue
                this.callbacks.enqueueMessage({
                    type: 'streamComplete',
                    sourceId: this.source.id,
                    totalPhotos: this.streamPhotos.length,
                    duration
                });
                break;

            case 'error':
                console.error('PhotoLoadingProcess: Stream error:', data.message);
                this.callbacks.onError?.(new Error(data.message || 'Unknown stream error'));
                break;

            default:
                console.warn('PhotoLoadingProcess: Unknown stream message type:', data.type);
        }
    }

    private checkAborted(): void {
        if (this.abortController?.signal.aborted) {
            throw new Error('Loading cancelled');
        }
    }

    // Public interface
    cancel(): void {
        console.log('PhotoLoadingProcess: Cancelling load');

        if (this.abortController && !this.abortController.signal.aborted) {
            this.abortController.abort();
        }

        if (this.eventSource) {
            this.eventSource.close();
        }
    }

    isAborted(): boolean {
        return this.abortController?.signal.aborted || false;
    }

    isFinished(): boolean {
        return this.isComplete;
    }

    isLoading(): boolean {
        return !this.isComplete && !this.isAborted();
    }

    getDuration(): number {
        return Date.now() - this.startTime;
    }

    getSource(): SourceConfig {
        return this.source;
    }

    // Data access
    getAllPhotos(): PhotoData[] {
        if (this.source.type === 'json') {
            const cachedPhotos = this.callbacks.getCachedJson?.(this.source.id);
            return cachedPhotos ? [...cachedPhotos] : [];
        } else if (this.source.type === 'stream') {
            return [...this.streamPhotos];
        }
        return [];
    }

    getFilteredPhotos(bounds: Bounds): PhotoData[] {
        if (this.source.type === 'json') {
            const cachedPhotos = this.callbacks.getCachedJson?.(this.source.id);
            return cachedPhotos ? filterPhotosByArea(cachedPhotos, bounds) : [];
        } else if (this.source.type === 'stream') {
            // Stream sources handle bounds filtering server-side
            return [...this.streamPhotos];
        }
        return [];
    }
}