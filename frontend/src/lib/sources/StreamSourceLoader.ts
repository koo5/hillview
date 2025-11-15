/**
 * Stream Source Loader - Loads photos from streaming endpoints
 * Uses EventSource for real-time photo streaming with bounds-based filtering
 */

import type { PhotoData, Bounds } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import { verbalizeEventSourceReadyState } from './eventSourceUtils';
import { postToast } from '../workerToast';
import type { PhotoSourceOptions } from './PhotoSourceFactory';

export class StreamSourceLoader extends BasePhotoSourceLoader {
    private eventSource?: EventSource;
    private streamPhotos: PhotoData[] = [];
    private completionPromise?: Promise<void>;
    private completionResolve?: () => void;
    private timeoutId?: NodeJS.Timeout;
    private readyStateMonitorId?: NodeJS.Timeout;
    private wasConnected = false;
	private wasErrored = false;
    private retryCount = 0;
    private maxRetries = 1; // Only retry once for auth errors
    private currentBounds?: Bounds;
    private maxPhotos?: number;

    constructor(source: any, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions) {
        super(source, callbacks);
        this.maxPhotos = options?.maxPhotos;
    }

    private async getAuthTokenWithTimeout(timeoutMs: number = 5000, forceRefresh: boolean = false): Promise<string | null> {
        const tokenPromise = this.callbacks.getValidToken(forceRefresh);
        const timeoutPromise = new Promise<null>((_, reject) => {
            setTimeout(() => reject(new Error('Token request timeout')), timeoutMs);
        });

        return await Promise.race([tokenPromise, timeoutPromise]);
    }

    private handleFinalFailure(errorMessage: string, shouldShowToast: boolean): void {
        // Mark as complete on final error
        this.isComplete = true;

        this.updateLoadingStatus(false, undefined, errorMessage);
        this.callbacks.onError?.(new Error(errorMessage));

        // Show toast based on pre-completion state
        if (shouldShowToast) {
            console.log(`🔍 StreamSourceLoader: Showing Connection lost toast for ${this.source.id} (connection lost during streaming)`);
            postToast('error', 'Connection lost', this.source.name || this.source.id, 0);
        } else {
            console.log(`🔍 StreamSourceLoader: NOT showing Connection lost toast for ${this.source.id}`, {
                reason: !this.wasConnected ? 'never connected' : 'stream already completed'
            });
        }
        this.wasConnected = false;
        this.wasErrored = true;

        // Resolve the completion promise even on error to prevent hanging
        this.resolveCompletion();
    }

    private updateLoadingStatus(isLoading: boolean, progress?: string, error?: string): void {
        // StreamSourceLoader runs only in worker context
        // Send loading status updates via postMessage to main thread
        if (typeof postMessage === 'function') {
            postMessage({
                type: 'sourceLoadingStatus',
                source_id: this.source.id,
                is_loading: isLoading,
                progress,
                error
            });
        }
    }

    async start(bounds?: Bounds): Promise<void> {
        if (!bounds) {
            // Stream sources without bounds are valid during config setup
            // They will be started with bounds later when area is updated
            //console.log(`StreamSourceLoader: Started ${this.source.id} without bounds - waiting for area update`);
            this.isComplete = true;
            return;
        }

        this.currentBounds = bounds;
        return this.attemptConnection(bounds);
    }

    private async attemptConnection(bounds: Bounds): Promise<void> {
        if (!this.source.url) {
            throw new Error('Stream source missing URL');
        }

        console.log(`StreamSourceLoader: Starting stream from ${this.source.url} (attempt ${this.retryCount + 1}/${this.maxRetries + 1})`);

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
        const clientId = this.source.clientId || 'default';
        url.searchParams.set('client_id', clientId);

        // Add max_photos parameter if specified
        if (this.maxPhotos !== undefined) {
            url.searchParams.set('max_photos', this.maxPhotos.toString());
        }

        // Add authentication token (force refresh on retry attempts)
        try {
            const forceRefresh = this.retryCount > 0;
            const authToken = await this.getAuthTokenWithTimeout(5000, forceRefresh);
            if (authToken) {
                url.searchParams.set('token', authToken);
                console.log(`StreamSourceLoader: Authenticated request for ${this.source.id}${forceRefresh ? ' (with refreshed token)' : ''}`);
            } else {
                console.log(`StreamSourceLoader: Anonymous request for ${this.source.id}`);
            }
        } catch (error) {
            console.error(`StreamSourceLoader: Authentication failed for ${this.source.id}:`, error);
            const errorMessage = error instanceof Error ? error.message : String(error);
            throw new Error(`Authentication failed: ${errorMessage}`);
        }

        // Create completion promise with timeout
        this.completionPromise = new Promise<void>((resolve) => {
            this.completionResolve = resolve;
        });

        // Let OS handle connection lifecycle - no artificial timeout

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
                console.error('🢄StreamSourceLoader: Error parsing stream message:', error);
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
            console.log(`🔍 StreamSourceLoader: onerror triggered for ${this.source.id}`, {
                isComplete: this.isComplete,
                wasConnected: this.wasConnected,
                wasErrored: this.wasErrored,
                aborted: this.abortController?.signal.aborted,
                readyState: this.eventSource?.readyState ? verbalizeEventSourceReadyState(this.eventSource.readyState) : 'undefined',
                timeFromStart: Date.now() - this.startTime
            });

            // Check if stream is already complete - if so, this is normal connection closure
            if (this.isComplete) {
                console.log(`StreamSourceLoader: EventSource connection closed normally after stream completion for ${this.source.id}`);
                // Don't show "Connection lost" toast for normal stream completion
                this.wasConnected = false;
                console.log(`🔍 StreamSourceLoader: Set wasConnected=false for completed stream ${this.source.id}`);
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

            console.error('🢄StreamSourceLoader: Stream error details:', JSON.stringify({
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
                console.error('🢄StreamSourceLoader: EventSource failed immediately after creation - possible network/CORS/URL issue');
            }

            // Check if we should show toast BEFORE marking as complete
            const shouldShowToast = this.wasConnected && !this.isComplete;
            console.log(`🔍 StreamSourceLoader: Checking toast conditions for ${this.source.id}`, {
                wasConnected: this.wasConnected,
                isComplete: this.isComplete,
                willShowToast: shouldShowToast
            });

            // Clean up the current EventSource on error
            if (this.eventSource) {
                console.log(`StreamSourceLoader: Closing EventSource on error for ${this.source.id}`);
                this.eventSource.close();
                this.eventSource = undefined;
            }

            // Check if this could be an auth error and we should retry
            const timeFromStart = Date.now() - this.startTime;
            const isImmediateFailure = timeFromStart < 1000;
            const couldBeAuthError = !this.wasConnected && isImmediateFailure;
            const shouldRetry = couldBeAuthError && this.retryCount < this.maxRetries;

            if (shouldRetry) {
                console.log(`🔄 StreamSourceLoader: Retrying with fresh token for ${this.source.id} (attempt ${this.retryCount + 1}/${this.maxRetries + 1}) - possible auth error`);
                this.retryCount++;
                this.wasErrored = false; // Reset error state for retry
                this.isComplete = false; // Reset completion state

                // Retry with fresh token after a short delay
                setTimeout(() => {
                    if (this.currentBounds && !this.isAborted()) {
                        this.attemptConnection(this.currentBounds).catch((retryError) => {
                            console.error(`StreamSourceLoader: Retry failed for ${this.source.id}:`, retryError);
                            // After retry failure, show toast for genuine connection issues
                            const showToastAfterRetry = true; // Always show toast after retry failure
                            this.handleFinalFailure(errorMessage, showToastAfterRetry);
                        });
                    }
                }, 100);
                return; // Don't mark as complete yet, we're retrying
            }

            // No retry needed - handle final failure
            // Show toast if we had a connection before OR if this was not an immediate failure (genuine network issue)
            const shouldShowToastForGenuineError = shouldShowToast || (!couldBeAuthError && !this.wasConnected);
            this.handleFinalFailure(errorMessage, shouldShowToastForGenuineError);
        };

        this.eventSource.onopen = () => {
            const timeFromStart = Date.now() - this.startTime;
            console.log(`🔍 StreamSourceLoader: Stream opened for ${this.source.id}`, {
                readyState: this.eventSource ? verbalizeEventSourceReadyState(this.eventSource.readyState) : 'undefined',
                timeFromStart,
                wasErrored: this.wasErrored
            });
            this.updateLoadingStatus(true, 'Loading photos...');

            // Toast only on reconnection
            if (this.wasErrored) {
                postToast('success', 'Connection restored', this.source.name || this.source.id, 3000);
            }
			this.wasErrored= false;
            this.wasConnected = true;
            console.log(`🔍 StreamSourceLoader: Set wasConnected=true for ${this.source.id} after ${timeFromStart}ms`);
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

                    const convertedPhotos: PhotoData[] = data.photos.map((photo: any) => {
                        const convertedPhoto: any = {
                            id: photo.id,
                            uid: `${this.source.id}-${photo.id}`,
                            coord: photo.geometry ?
                                { lat: photo.geometry.coordinates[1], lng: photo.geometry.coordinates[0] } :
                                photo.coord,
                            bearing: photo.computed_bearing || photo.bearing || 0,
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
                        };

                        // Add file hash if available for deduplication with device photos
                        if (photo.file_md5) {
                            convertedPhoto.file_hash = photo.file_md5;
                        }

                        // Add creator information if available (from Mapillary API)
                        if (photo.creator && typeof photo.creator === 'object') {
                            convertedPhoto.creator = {
                                id: photo.creator.id,
                                username: photo.creator.username
                            };
                        }

                        return convertedPhoto;
                    });

                    this.streamPhotos.push(...convertedPhotos);

                    // Send message to worker queue for each batch
                    this.callbacks.enqueueMessage({
                        type: 'photosAdded',
                        source_id: this.source.id,
                        photos: this.streamPhotos, // Send accumulated photos (growing list)
                    });
                }
                break;

            case 'stream_complete':
                console.log(`🔍 StreamSourceLoader: Stream complete for ${this.source.id}`, {
                    wasConnected: this.wasConnected,
                    wasErrored: this.wasErrored,
                    totalPhotos: this.streamPhotos.length
                });
                this.isComplete = true;
                const duration = Date.now() - this.startTime;

                // Update loading status to complete
                this.updateLoadingStatus(false, `Loaded ${this.streamPhotos.length} photos`);

                // Send completion message to worker queue
                this.callbacks.enqueueMessage({
                    type: 'streamComplete',
                    source_id: this.source.id,
                    totalPhotos: this.streamPhotos.length,
                    duration
                });

                // Close EventSource since stream is complete
                if (this.eventSource) {
                    console.log(`🔍 StreamSourceLoader: Closing EventSource after stream completion for ${this.source.id} (wasConnected=${this.wasConnected})`);
                    this.eventSource.close();
                    this.eventSource = undefined; // Clear reference to allow garbage collection
                }

                // Resolve the completion promise
                this.resolveCompletion();
                break;

            case 'error':
                console.error('🢄StreamSourceLoader: Stream error:', data.message);
                this.updateLoadingStatus(false, undefined, data.message || 'Unknown stream error');
                this.callbacks.onError?.(new Error(data.message || 'Unknown stream error'));
                // Resolve the completion promise even on error
                this.resolveCompletion();
                break;

            default:
                console.info('🢄StreamSourceLoader: Unknown stream message type:', data.type);
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

        // Resolve completion promise if still pending
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
