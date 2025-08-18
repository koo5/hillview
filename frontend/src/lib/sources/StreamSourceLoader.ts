/**
 * Stream Source Loader - Loads photos from streaming endpoints
 * Uses EventSource for real-time photo streaming with bounds-based filtering
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import { verbalizeEventSourceReadyState } from './eventSourceUtils';

export class StreamSourceLoader extends BasePhotoSourceLoader {
    private eventSource?: EventSource;
    private streamPhotos: PhotoData[] = [];
    private completionPromise?: Promise<void>;
    private completionResolve?: () => void;
    private timeoutId?: NodeJS.Timeout;
    private readyStateMonitorId?: NodeJS.Timeout;

    constructor(source: any, callbacks: PhotoSourceCallbacks) {
        super(source, callbacks);
    }

    private updateLoadingStatus(isLoading: boolean, progress?: string, error?: string): void {
        // StreamSourceLoader runs only in worker context
        // Send loading status updates via postMessage to main thread
        if (typeof postMessage === 'function') {
            postMessage({
                type: 'sourceLoadingStatus',
                sourceId: this.source.id,
                isLoading,
                progress,
                error
            });
        }
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
        
        // Create abort controller for this request
        this.abortController = new AbortController();

        // Set loading status
        this.updateLoadingStatus(true, 'Connecting...');

        // Build URL with bounds parameters (using server-expected parameter names)
        const url = new URL(this.source.url);
        url.searchParams.set('top_left_lat', bounds.top_left.lat.toString());
        url.searchParams.set('top_left_lon', bounds.top_left.lng.toString()); // Changed from top_left_lng
        url.searchParams.set('bottom_right_lat', bounds.bottom_right.lat.toString());
        url.searchParams.set('bottom_right_lon', bounds.bottom_right.lng.toString()); // Changed from bottom_right_lng

        // Add client_id parameter (required by server)
        const clientId = this.source.clientId || 'default'; // Provide default if not specified
        url.searchParams.set('client_id', clientId);
        
        // Add JWT token if provided in source configuration (for EventSource authentication)
        if (this.source.authToken) {
            url.searchParams.set('token', this.source.authToken);
            console.log(`StreamSourceLoader: Adding authentication token to ${this.source.id} request`);
        } else {
            console.log(`StreamSourceLoader: No authentication token provided for ${this.source.id} request`);
        }

        // Create completion promise with timeout
        this.completionPromise = new Promise<void>((resolve) => {
            this.completionResolve = resolve;
        });

        // Add timeout to prevent hanging forever (2 minutes to match server timeouts)
        this.timeoutId = setTimeout(() => {
            console.warn(`StreamSourceLoader: Timeout waiting for ${this.source.url} - closing connection`);
            // Mark as complete on timeout
            this.isComplete = true;
            // Properly close the EventSource on timeout
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = undefined;
            }
            this.updateLoadingStatus(false, undefined, 'Connection timeout');
            this.resolveCompletion();
        }, 120000); // 2 minutes

        this.eventSource = new EventSource(url.toString());
        console.log(`StreamSourceLoader: Created EventSource for ${this.source.id} with URL:`, url.toString());
        console.log(`StreamSourceLoader: Initial EventSource readyState: ${verbalizeEventSourceReadyState(this.eventSource.readyState)}`);
        
        // Connect abort signal to EventSource
        this.abortController.signal.addEventListener('abort', () => {
            console.log(`StreamSourceLoader: Abort signal received, closing EventSource for ${this.source.id}`);
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = undefined; // Clear reference to allow garbage collection
            }
            this.resolveCompletion();
        });

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamMessage(data);
            } catch (error) {
                console.error('StreamSourceLoader: Error parsing stream message:', error);
                this.callbacks.onError?.(new Error('Error parsing stream data'));
                // Close EventSource on parsing error to prevent further errors
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = undefined;
                }
                this.updateLoadingStatus(false, undefined, 'Failed to parse stream data');
                this.resolveCompletion();
            }
        };

        this.eventSource.onerror = (error) => {
            // Check if stream is already complete - if so, this is normal connection closure
            if (this.isComplete) {
                console.log(`StreamSourceLoader: EventSource connection closed normally after stream completion for ${this.source.id}`);
                return;
            }
            
            // Check if we've been cancelled/aborted
            if (this.abortController?.signal.aborted) {
                console.log(`StreamSourceLoader: EventSource error after abort for ${this.source.id} - ignoring`);
                return;
            }
            
            // Extract more meaningful error information
            let errorMessage = 'Stream connection error for ' + this.source.id + ' (' + this.source.url + ')';
            if (error instanceof ErrorEvent) {
                errorMessage = `Stream error: ${error.message || error.type || 'Unknown error'}`;
            } else if (error && typeof error === 'object') {
                errorMessage = `Stream error: ${JSON.stringify(error, Object.getOwnPropertyNames(error))}`;
            }
            
            console.error('StreamSourceLoader: Stream error details:', JSON.stringify({
                error,
                errorType: error?.constructor?.name,
                errorMessage,
                readyState: this.eventSource?.readyState ? verbalizeEventSourceReadyState(this.eventSource.readyState) : 'undefined',
                url: this.eventSource?.url,
                timeFromCreation: Date.now() - this.startTime,
                connectionState: navigator.onLine ? 'online' : 'offline',
                isComplete: this.isComplete
            }, null, 2));
            
            // Check if this is an immediate connection failure
            if (this.eventSource?.readyState === EventSource.CLOSED && Date.now() - this.startTime < 1000) {
                console.error('StreamSourceLoader: EventSource failed immediately after creation - possible network/CORS/URL issue');
            }
            
            // Mark as complete on error to prevent further processing
            this.isComplete = true;
            
            // Clean up the EventSource on error
            if (this.eventSource) {
                console.log(`StreamSourceLoader: Closing EventSource on error for ${this.source.id}`);
                this.eventSource.close();
                this.eventSource = undefined;
            }
            
            this.updateLoadingStatus(false, undefined, errorMessage);
            this.callbacks.onError?.(new Error(errorMessage));
            // Resolve the completion promise even on error to prevent hanging
            this.resolveCompletion();
        };

        this.eventSource.onopen = () => {
            console.log(`StreamSourceLoader: Stream opened for ${this.source.id} (readyState: ${this.eventSource ? verbalizeEventSourceReadyState(this.eventSource.readyState) : 'undefined'})`);
            this.updateLoadingStatus(true, 'Loading photos...');
        };

        // Monitor readyState changes
        let lastReadyState = this.eventSource.readyState;
        this.readyStateMonitorId = setInterval(() => {
            if (this.eventSource && this.eventSource.readyState !== lastReadyState) {
                console.log(`StreamSourceLoader: ReadyState changed from ${verbalizeEventSourceReadyState(lastReadyState)} to ${verbalizeEventSourceReadyState(this.eventSource.readyState)} for ${this.source.id}`);
                lastReadyState = this.eventSource.readyState;
                if (this.eventSource.readyState === EventSource.CLOSED) {
                    if (this.readyStateMonitorId) {
                        clearInterval(this.readyStateMonitorId);
                        this.readyStateMonitorId = undefined;
                    }
                }
            }
        }, 100);

        // Clear monitor on abort
        this.abortController.signal.addEventListener('abort', () => {
            if (this.readyStateMonitorId) {
                clearInterval(this.readyStateMonitorId);
                this.readyStateMonitorId = undefined;
            }
        });

        // Return the completion promise
        return this.completionPromise;
    }

    private resolveCompletion(): void {
        // Clear timeout and resolve promise
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = undefined;
        }
        // Clear readyState monitor
        if (this.readyStateMonitorId) {
            clearInterval(this.readyStateMonitorId);
            this.readyStateMonitorId = undefined;
        }
        if (this.completionResolve) {
            this.completionResolve();
            this.completionResolve = undefined;
            this.completionPromise = undefined;
        }
        // Ensure EventSource is cleaned up
        if (this.eventSource) {
            console.log(`StreamSourceLoader: Cleaning up EventSource in resolveCompletion for ${this.source.id}`);
            this.eventSource.close();
            this.eventSource = undefined;
        }
    }

    private handleStreamMessage(data: any): void {
        switch (data.type) {
            case 'photos':
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
                        hasNext: !!data.hasNext // Preserve hasNext for client caching decisions
                    });
                }
                break;

            case 'stream_complete':
                console.log(`StreamSourceLoader: Stream complete for ${this.source.id}`);
                this.isComplete = true;
                const duration = Date.now() - this.startTime;
                
                // Update loading status to complete
                this.updateLoadingStatus(false, `Loaded ${this.streamPhotos.length} photos`);
                
                // Send completion message to worker queue
                this.callbacks.enqueueMessage({
                    type: 'streamComplete',
                    sourceId: this.source.id,
                    totalPhotos: this.streamPhotos.length,
                    duration
                });

                // Close EventSource since stream is complete
                if (this.eventSource) {
                    console.log(`StreamSourceLoader: Closing EventSource after stream completion for ${this.source.id}`);
                    this.eventSource.close();
                    this.eventSource = undefined; // Clear reference to allow garbage collection
                }

                // Resolve the completion promise
                this.resolveCompletion();
                break;

            case 'error':
                console.error('StreamSourceLoader: Stream error:', data.message);
                this.updateLoadingStatus(false, undefined, data.message || 'Unknown stream error');
                this.callbacks.onError?.(new Error(data.message || 'Unknown stream error'));
                // Resolve the completion promise even on error
                this.resolveCompletion();
                break;

            default:
                console.warn('StreamSourceLoader: Unknown stream message type:', data.type);
        }
    }

    cancel(): void {
        console.log(`StreamSourceLoader: Cancelling stream for ${this.source.id} - called from:`, new Error().stack?.split('\n')[2]);
        super.cancel();
        
        // Clear loading status
        this.updateLoadingStatus(false, 'Cancelled');
        
        // Clear readyState monitor first
        if (this.readyStateMonitorId) {
            clearInterval(this.readyStateMonitorId);
            this.readyStateMonitorId = undefined;
        }
        
        if (this.eventSource) {
            console.log(`StreamSourceLoader: Closing EventSource for ${this.source.id} (readyState: ${verbalizeEventSourceReadyState(this.eventSource.readyState)})`);
            this.eventSource.close();
            this.eventSource = undefined; // Clear reference to allow garbage collection
        }

        // Clear timeout and resolve completion promise if still pending
        this.resolveCompletion();
        
        // Clear all data and references
        this.streamPhotos = [];
        this.completionPromise = undefined;
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