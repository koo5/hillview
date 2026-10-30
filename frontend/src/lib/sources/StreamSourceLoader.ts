/**
 * Stream Source Loader - Loads photos from streaming endpoints
 *
 * Reads the server-sent-events stream with fetch rather than EventSource, for
 * two reasons. fetch can send the access token in an Authorization header;
 * EventSource cannot, which used to put the token in the URL and so in every
 * access log on the way. And fetch exposes the HTTP status, so a rejected token
 * (401, retried once with a forcibly refreshed one) is told apart from a
 * network failure instead of guessed at from timing.
 *
 * The backend still accepts `?token=` on the stream endpoints: the released
 * Tauri build's Kotlin loader sends it, and must keep working.
 */

import type { PhotoData, Bounds, PhotoId } from '../photoWorkerTypes';
import { BasePhotoSourceLoader, type PhotoSourceCallbacks } from './PhotoSourceLoader';
import { postToast } from '../workerToast';
import type { PhotoSourceOptions } from './PhotoSourceFactory';
import { STREAM_INACTIVITY_TIMEOUT_MS } from '../photoWorkerConstants';

const LOG_PREFIX = '🢄🔍StreamSourceLoader';
const doLog = false;

export function convertStreamPhoto(photo: any, source: any): PhotoData {
    let bearing = photo.computed_compass_angle
    if (bearing === undefined || bearing === null) {
        bearing = photo.compass_angle
    }
    if (bearing === undefined || bearing === null) {
        bearing = photo.bearing
    }
    const hasBearing = !(bearing === undefined || bearing === null);
    if (!hasBearing) {
        console.warn(`StreamSourceLoader: Photo ${photo.id} missing bearing info, defaulting to 0`);
        bearing = 0
    }

    // Map Mapillary thumbnail sizes to the viewer's `sizes`. thumb_original_url
    // (full resolution) becomes `full`, which the zoom viewers prefer — OpenSeadragon
    // for flat photos and Pannellum for 360° panoramas (otherwise they fall back to
    // the 1024px thumb).
    const mapillarySizes: Record<string, { url: string; width: number; height: number }> = {};
    if (photo.thumb_1024_url) {
        mapillarySizes['1024'] = { url: photo.thumb_1024_url, width: 1024, height: 768 };
    }
    if (photo.thumb_original_url) {
        mapillarySizes.full = { url: photo.thumb_original_url, width: 0, height: 0 };
    }

    const convertedPhoto: any = {
        id: photo.id,
        uid: `${source.id}-${photo.id}`,
        coord: photo.geometry ?
            { lat: photo.geometry.coordinates[1], lng: photo.geometry.coordinates[0] } :
            photo.coord,
        bearing,
        ...(hasBearing ? {} : { has_bearing: false }),
        url: photo.thumb_1024_url || photo.url || '',
        filename: photo.filename,
        source_type: source.type,
        source,
        altitude: photo.computed_altitude || photo.altitude || 0,
        captured_at: photo.captured_at,
        is_pano: photo.is_pano,
        sizes: photo.sizes || (Object.keys(mapillarySizes).length > 0 ? mapillarySizes : undefined)
    };

    if (photo.title) {
        convertedPhoto.title = photo.title;
    }

    if (photo.description) {
        convertedPhoto.description = photo.description;
    }

    if (photo.keywords) {
        convertedPhoto.keywords = photo.keywords;
    }

    if (photo.featured) {
        convertedPhoto.featured = true;
    }

    // Mapillary flags 360° panoramas with is_pano; surface it via the shared
    // `projection` field that the zoom viewer routes on (same as Panoramax).
    if (photo.is_pano) {
        convertedPhoto.projection = 'equirectangular';
    }

    if (photo.filtered) {
        convertedPhoto.filtered = true;
    }

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

    if (photo.license) {
        convertedPhoto.license = photo.license;
    }

    return convertedPhoto;
}

/**
 * Incremental parser for a `text/event-stream` body. Lines may arrive split
 * across chunks and end in LF, CRLF or CR. A blank line dispatches the event's
 * `data:` lines (joined with newlines), as EventSource does; comments, `id:`
 * and `retry:` are ignored, and named events (`event: x`) are skipped because
 * EventSource's onmessage never saw them either. An unterminated final event
 * is dropped, also as EventSource does.
 */
export class SseDataParser {
    private buffer = '';
    private dataLines: string[] = [];
    private eventType = '';
    // The previous chunk ended in a CR, which may be the first half of a CRLF.
    private pendingCr = false;

    constructor(private readonly onData: (data: string) => void) {}

    push(text: string): void {
        if (this.pendingCr && text.length > 0) {
            if (text.startsWith('\n')) text = text.slice(1);
            this.pendingCr = false;
        }
        this.buffer += text;
        for (;;) {
            const match = /\r\n|\r|\n/.exec(this.buffer);
            if (!match) return;
            const line = this.buffer.slice(0, match.index);
            this.buffer = this.buffer.slice(match.index + match[0].length);
            // A CR is a complete line ending on its own; skip the LF of a CRLF
            // whose two halves arrive in different chunks.
            if (match[0] === '\r' && this.buffer === '') this.pendingCr = true;
            this.processLine(line);
        }
    }

    private processLine(line: string): void {
        if (line === '') {
            const data = this.dataLines.join('\n');
            const isMessage = this.eventType === '' || this.eventType === 'message';
            const hasData = this.dataLines.length > 0;
            this.dataLines = [];
            this.eventType = '';
            if (hasData && isMessage) this.onData(data);
            return;
        }
        if (line.startsWith(':')) return;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        let value = colon === -1 ? '' : line.slice(colon + 1);
        if (value.startsWith(' ')) value = value.slice(1);
        if (field === 'data') this.dataLines.push(value);
        else if (field === 'event') this.eventType = value;
    }
}

function describeError(error: unknown): string {
    return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

export class StreamSourceLoader extends BasePhotoSourceLoader {
    // The open stream request. Aborting it ends the request without cancelling
    // the loader, the way EventSource.close() used to; the loader itself is
    // cancelled through the base class's abortController.
    private connection?: AbortController;
    private streamPhotos: PhotoData[] = [];
    private completionPromise?: Promise<void>;
    private completionResolve?: () => void;
    private timeoutId?: NodeJS.Timeout;
    private wasConnected = false;
	private wasErrored = false;
    private retryCount = 0;
    private maxRetries = 1; // One retry for a request that failed before the stream opened
    // Status of the failure that triggered the pending retry; a 401 makes the
    // retry force a token refresh.
    private retryAfterStatus?: number;
    private currentBounds?: Bounds;
    private maxPhotos?: number;
    private picks?: Set<PhotoId>;
    private queryOptionsJson?: string | null;  // Pre-serialized Hillview filters
    // Watchdog: a stream that goes silent (no event, no error) would otherwise
    // never resolve start(), and the area process it belongs to would never
    // complete. Re-armed on open and on every event.
    private inactivityTimeoutMs: number;
    private inactivityTimerId?: ReturnType<typeof setTimeout>;

    constructor(source: any, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions) {
        super(source, callbacks);
        this.maxPhotos = options?.maxPhotos;
        this.picks = options?.picks;
        this.queryOptionsJson = options?.queryOptionsJson;
        this.inactivityTimeoutMs = options?.streamInactivityTimeoutMs ?? STREAM_INACTIVITY_TIMEOUT_MS;
    }

    private armWatchdog(): void {
        this.disarmWatchdog();
        if (!(this.inactivityTimeoutMs > 0)) return;
        this.inactivityTimerId = setTimeout(() => {
            this.inactivityTimerId = undefined;
            if (this.isComplete || this.isAborted()) return;
            console.warn(`${LOG_PREFIX}: no stream activity for ${this.inactivityTimeoutMs}ms on ${this.source.id} - giving up`);
            this.closeConnection();
            // A stall after data flowed is a lost connection (toast); a stall
            // before anything arrived reads as the server never answering.
            this.handleFinalFailure(`Stream timed out after ${this.inactivityTimeoutMs}ms of silence`, this.wasConnected);
        }, this.inactivityTimeoutMs);
    }

    private disarmWatchdog(): void {
        if (this.inactivityTimerId) {
            clearTimeout(this.inactivityTimerId);
            this.inactivityTimerId = undefined;
        }
    }

    private closeConnection(): void {
        if (this.connection) {
            this.connection.abort();
            this.connection = undefined;
        }
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
            console.log(`${LOG_PREFIX}: Showing Connection lost toast for ${this.source.id} (connection lost during streaming)`);
            postToast('error', 'Connection lost', this.source.name || this.source.id, 0);
        } else {
            console.log(`${LOG_PREFIX}: NOT showing Connection lost toast for ${this.source.id}`, {
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

        if (doLog) console.log(`StreamSourceLoader: Starting stream from ${this.source.url} (attempt ${this.retryCount + 1}/${this.maxRetries + 1})`);

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

        // Add picks parameter if there are any selected photos
        if (this.picks && this.picks.size > 0) {
            // Convert Set to Array and join with comma
            url.searchParams.set('picks', Array.from(this.picks).join(','));
        }

        // Add client_id parameter (required by server)
        const clientId = this.source.client_id || 'default';
        url.searchParams.set('client_id', clientId);

        // Add max_photos parameter if specified
        if (this.maxPhotos !== undefined) {
            url.searchParams.set('max_photos', this.maxPhotos.toString());
        }

        // Add filters parameter if pre-serialized filters are provided
        if (this.queryOptionsJson) {
            url.searchParams.set('filters', this.queryOptionsJson);
        }

        // Authorization header. A retry after a 401 forces a token refresh; a
        // retry after a network failure or a 5xx reuses the token it had.
        // No Cache-Control request header: it is not in the API's CORS
        // allow-list, and `cache: 'no-store'` below does the job without one.
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        try {
            const forceRefresh = this.retryCount > 0 && this.retryAfterStatus === 401;
            const authToken = await this.getAuthTokenWithTimeout(5000, forceRefresh);
            if (authToken) {
                headers.Authorization = `Bearer ${authToken}`;
                console.log(`StreamSourceLoader: Authenticated request for ${this.source.id}${forceRefresh ? ' (with refreshed token)' : ''}`);
            } else {
                console.log(`StreamSourceLoader: Anonymous request for ${this.source.id}`);
            }
        } catch (error) {
            console.error(`StreamSourceLoader: Authentication failed for ${this.source.id}:`, error);
            const errorMessage = error instanceof Error ? error.message : String(error);
            throw new Error(`Authentication failed: ${errorMessage}`);
        }

        // Create completion promise only if one doesn't already exist (retries reuse the original)
        if (!this.completionPromise) {
            this.completionPromise = new Promise<void>((resolve) => {
                this.completionResolve = resolve;
            });
        }

        // Let OS handle connection lifecycle - no artificial timeout

        const connection = new AbortController();
        this.connection = connection;

        // Cancelling the loader ends the request
        this.abortController.signal.addEventListener('abort', () => {
            if (doLog) console.log(`StreamSourceLoader: Abort signal received, closing stream for ${this.source.id}`);
            this.closeConnection();
            this.resolveCompletion();
        });

        this.armWatchdog();
        void this.readStream(url.toString(), headers, connection);

        // Return the completion promise
        return this.completionPromise;
    }

    /**
     * Run one stream request to its end. Every exit after `connection` was
     * aborted is silent: the abort came from this loader (cancel, watchdog,
     * stream completion, a stream error message), which has already settled
     * the outcome.
     */
    private async readStream(url: string, headers: Record<string, string>, connection: AbortController): Promise<void> {
        let response: Response;
        try {
            response = await fetch(url, { headers, signal: connection.signal, cache: 'no-store' });
        } catch (error) {
            if (connection.signal.aborted) return;
            this.handleConnectionError(`Stream request failed for ${this.source.id}: ${describeError(error)}`);
            return;
        }
        if (connection.signal.aborted) return;

        if (!response.ok || !response.body) {
            const detail = await response.text().catch(() => '');
            if (connection.signal.aborted) return;
            this.handleConnectionError(
                `Stream request failed for ${this.source.id}: HTTP ${response.status}${detail ? ` ${detail.slice(0, 200)}` : ''}`,
                response.status
            );
            return;
        }

        this.handleOpen();

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const parser = new SseDataParser((data) => {
            // An event earlier in the same chunk may have closed the stream
            // (stream_complete, an error message); EventSource dispatched
            // nothing after close() either.
            if (connection.signal.aborted) return;
            this.handleEventData(data);
        });
        try {
            for (;;) {
                const { value, done } = await reader.read();
                if (done) break;
                parser.push(decoder.decode(value, { stream: true }));
                if (connection.signal.aborted) return;
            }
        } catch (error) {
            if (connection.signal.aborted) return;
            this.handleConnectionError(`Stream connection lost for ${this.source.id}: ${describeError(error)}`);
            return;
        }
        if (connection.signal.aborted) return;
        // The server ended the body without sending stream_complete.
        this.handleConnectionError(`Stream for ${this.source.id} ended before completion`);
    }

    private handleOpen(): void {
        const timeFromStart = Date.now() - this.startTime;
        if (doLog) console.log(`${LOG_PREFIX}: Stream opened for ${this.source.id}`, {
            timeFromStart,
            wasErrored: this.wasErrored
        });
        this.updateLoadingStatus(true, 'Loading photos...');
        this.armWatchdog();

        // Toast only on reconnection
        if (this.wasErrored) {
            postToast('success', 'Connection restored', this.source.name || this.source.id, 3000);
        }
		this.wasErrored= false;
        this.wasConnected = true;
        if (doLog) console.log(`${LOG_PREFIX}: Set wasConnected=true for ${this.source.id} after ${timeFromStart}ms`);
    }

    private handleEventData(data: string): void {
        this.armWatchdog();
        try {
            const parsed = JSON.parse(data);
            this.handleStreamMessage(parsed);
        } catch (error) {
            console.error('🢄🔍StreamSourceLoader: Error parsing stream message:', error);
            this.callbacks.onError?.(new Error('Error parsing stream data'));
            // Close the stream on parsing error to prevent further errors
            this.closeConnection();
            this.updateLoadingStatus(false, undefined, 'Failed to parse stream data');
            this.resolveCompletion();
        }
    }

    /**
     * The request failed, or the stream broke or ended early. `status` is the
     * HTTP status when the server answered with an error, undefined when no
     * answer came (network failure) or the stream broke after opening.
     */
    private handleConnectionError(errorMessage: string, status?: number): void {
        const timeFromStart = Date.now() - this.startTime;
        console.log(`${LOG_PREFIX}: stream failure for ${this.source.id}`, {
            status,
            isComplete: this.isComplete,
            wasConnected: this.wasConnected,
            wasErrored: this.wasErrored,
            aborted: this.abortController?.signal.aborted,
            timeFromStart
        });

        // Already complete: the server closing after stream_complete is normal
        if (this.isComplete) {
            this.wasConnected = false;
            return;
        }

        // Check if we've been cancelled/aborted
        if (this.abortController?.signal.aborted) {
            if (doLog) console.log(`StreamSourceLoader: stream error after abort for ${this.source.id} - ignoring`);
            return;
        }

        console.warn(`🢄StreamSourceLoader: ${errorMessage}`, JSON.stringify({
            status,
            timeFromStart,
            connectionState: navigator.onLine ? 'online' : 'offline'
        }));

        // Check if we should show toast BEFORE marking as complete
        const shouldShowToast = this.wasConnected && !this.isComplete;

        this.closeConnection();

        // Retry once a request that failed before the stream opened, unless the
        // server rejected the request itself (a 4xx other than 401). A 401
        // retries with a forcibly refreshed token.
        const retryableStatus = status === undefined || status === 401 || status >= 500;
        const shouldRetry = !this.wasConnected && retryableStatus && this.retryCount < this.maxRetries;

        if (shouldRetry) {
            console.log(`🔄 StreamSourceLoader: Retrying ${this.source.id}${status === 401 ? ' with a refreshed token' : ''} (attempt ${this.retryCount + 2}/${this.maxRetries + 1})`);
            this.retryCount++;
            this.retryAfterStatus = status;
            this.wasErrored = false; // Reset error state for retry
            this.isComplete = false; // Reset completion state

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

        // No retry - final failure. "Connection lost" when a stream that was
        // flowing broke, or when connecting failed slowly enough to be a real
        // network problem. Never for a rejected token: the session machinery
        // owns that.
        const isImmediateFailure = timeFromStart < 1000;
        const toastForConnectFailure = !this.wasConnected && !isImmediateFailure && status !== 401;
        this.handleFinalFailure(errorMessage, shouldShowToast || toastForConnectFailure);
    }

    private resolveCompletion(): void {
        this.disarmWatchdog();
        if (this.completionResolve) {
            this.completionResolve();
            this.completionResolve = undefined;
            this.completionPromise = undefined;
        }
        // Ensure the stream request is ended
        this.closeConnection();
    }

    private handleStreamMessage(data: any): void {
        switch (data.type) {
            case 'photos':
                if (data.photos && Array.isArray(data.photos)) {
                    if (doLog) console.log(`StreamSourceLoader: Received ${data.photos.length} photos`);

                    const convertedPhotos: PhotoData[] = data.photos.map((photo: any) => convertStreamPhoto(photo, this.source));

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
                console.log(`${LOG_PREFIX}: Stream complete for ${this.source.id}`, {
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

                // End the request since the stream is complete
                if (doLog) console.log(`${LOG_PREFIX}: Closing stream after completion for ${this.source.id} (wasConnected=${this.wasConnected})`);
                this.closeConnection();

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
        if (doLog) console.log(`StreamSourceLoader: Cancelling stream for ${this.source.id} - called from:`, new Error().stack?.split('\n')[2]);
        super.cancel();
        this.disarmWatchdog();

        // Clear loading status
        this.updateLoadingStatus(false, 'Cancelled');

        this.closeConnection();

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
