import {photosInArea, photosInRange, spatialState} from './mapState';
import {sourceLoadingStatus, sources} from './data.svelte';
import {get} from 'svelte/store';
import {getCurrentToken} from './auth.svelte';
import {createTokenManager} from './tokenManagerFactory';
import {addAlert} from './alertSystem.svelte';
import type {WorkerToastMessage} from './workerToast';

declare const __WORKER_VERSION__: string;


class SimplePhotoWorker {
    private worker: Worker | null = null;
    private frontendMessageId = 0;
    private isInitialized = false;
    private lastBounds: any = null;

    async initialize(): Promise<void> {
        if (this.worker && this.isInitialized) return;

        try {
            // Create worker directly
            this.worker = new Worker(
                new URL('./new.worker.ts', import.meta.url),
                {type: 'module'}
            );

            this.setupWorkerHandlers();

            // Initialize worker with config update including version check
            this.sendMessage('configUpdated', {
                config: {
                    expectedWorkerVersion: __WORKER_VERSION__
                }
            });
            this.isInitialized = true;

            // Set up reactive subscriptions
            this.setupReactivity();

            // Test: Check initial sources
            const initialSources = get(sources);
            console.log('🢄SimplePhotoWorker: Initial sources on startup:', JSON.stringify(
            initialSources.map(s => ({
                id: s.id,
                type: s.type,
                enabled: s.enabled,
                url: s.url,
                keys: Object.keys(s),
                JSON: JSON.stringify(s)
            }))));

        } catch (error) {
            console.error('🢄SimplePhotoWorker: Failed to initialize', error);
            throw error;
        }
    }

    private setupWorkerHandlers(): void {
        if (!this.worker) return;

        this.worker.onmessage = (e: MessageEvent) => {
            const message = e.data;
            // New worker only sends updates, no responses to track
            this.handleWorkerUpdate(message);
        };

        this.worker.onerror = (error: ErrorEvent) => {
            console.error('🢄SimplePhotoWorker: Worker error', error);
        };
    }

    private handleWorkerUpdate(message: any): void {
        switch (message.type) {
            case 'photosUpdate':
                // New worker sends raw photo arrays directly (no serialization needed)
                const areaPhotos = message.photosInArea || [];
                const rangePhotos = message.photosInRange || [];
                
                console.log(`SimplePhotoWorker: Updated photos - Area: ${areaPhotos.length}, Range: ${rangePhotos.length}, Range: ${message.currentRange}m`);
                
                photosInArea.set(areaPhotos);
                photosInRange.set(rangePhotos);
                break;

            case 'sourceLoadingStatus':
                // Handle loading status updates from worker
                sourceLoadingStatus.update(status => ({
                    ...status,
                    [message.sourceId]: {
                        isLoading: message.isLoading,
                        progress: message.progress,
                        error: message.error
                    }
                }));
                break;

            case 'error':
                console.error('🢄SimplePhotoWorker: Worker error', message.error);
                break;

            case 'toast':
                // Handle toast messages from worker
                const toastMessage = message as WorkerToastMessage;
                console.log(`SimplePhotoWorker: Received toast from worker: ${toastMessage.level} - ${toastMessage.message} (source: ${toastMessage.source})`);
                
                // Convert worker toast to main thread toast
                const duration = toastMessage.duration !== undefined ? toastMessage.duration : 
                    (toastMessage.level === 'error' ? 0 : 5000); // Persistent errors, auto-dismiss others
                
                addAlert(toastMessage.message, toastMessage.level, { duration, source: toastMessage.source });
                break;

            case 'getAuthToken':
                // Handle auth token requests from worker
                this.handleAuthTokenRequest(message.forceRefresh);
                break;
                
            default:
                console.warn('🢄SimplePhotoWorker: Unknown message type:', message.type);
        }
    }

    private async handleAuthTokenRequest(forceRefresh: boolean = false): Promise<void> {
        try {
            // Use the token manager to get a token with optional force refresh
            const tokenManager = createTokenManager();
            const currentToken = await tokenManager.getValidToken(forceRefresh);
            console.log(`SimplePhotoWorker: Sending auth token to worker: ${currentToken ? 'token available' : 'no token'}${forceRefresh ? ' (refreshed)' : ''}`);
            
            this.worker?.postMessage({
                type: 'authToken',
                token: currentToken
            });
        } catch (error) {
            console.error('SimplePhotoWorker: Error getting auth token for worker:', error);
            this.worker?.postMessage({
                type: 'authToken',
                token: null
            });
        }
    }

    private boundsChangeSignificant(oldBounds: any, newBounds: any): number {
        // Calculate old area dimensions
        const oldHeight = Math.abs(oldBounds.top_left.lat - oldBounds.bottom_right.lat);
        const oldWidth = Math.abs(oldBounds.bottom_right.lng - oldBounds.top_left.lng);
        
        // 10% threshold distances
        const latThreshold = oldHeight * 0.1;
        const lngThreshold = oldWidth * 0.1;
        
        // Check if both corners are within threshold distances
        const topLeftLatDiff = Math.abs(newBounds.top_left.lat - oldBounds.top_left.lat);
        const topLeftLngDiff = Math.abs(newBounds.top_left.lng - oldBounds.top_left.lng);
        const bottomRightLatDiff = Math.abs(newBounds.bottom_right.lat - oldBounds.bottom_right.lat);
        const bottomRightLngDiff = Math.abs(newBounds.bottom_right.lng - oldBounds.bottom_right.lng);
        
        const topLeftWithinThreshold = topLeftLatDiff <= latThreshold && topLeftLngDiff <= lngThreshold;
        const bottomRightWithinThreshold = bottomRightLatDiff <= latThreshold && bottomRightLngDiff <= lngThreshold;
        
        // Return 0 if both corners are within threshold (no significant change), 1 otherwise
        return (topLeftWithinThreshold && bottomRightWithinThreshold) ? 0 : 1;
    }

    private setupReactivity(): void {
        // React to spatial changes - triggers area updates with hysteresis
        spatialState.subscribe((spatial) => {
            if (!this.isInitialized || !spatial.bounds) return;

            // Skip update if bounds haven't changed significantly (hysteresis)
			// TODO: we could skip area load, but we can't skip range filter
            /*if (this.lastBounds && this.boundsChangeSignificant(this.lastBounds, spatial.bounds) < 0.003) {
                console.log('🢄SimplePhotoWorker: Skipping area update - bounds change too small');
                return;
            }*/

            console.log(`SimplePhotoWorker: Sending area update with range ${spatial.range}m...`);
            this.lastBounds = spatial.bounds;
            this.sendMessage('areaUpdated', {
                area: spatial.bounds,
                range: spatial.range
            });
        });

        // React to source changes - triggers config updates
        sources.subscribe(async (sourceList) => {
            if (!this.isInitialized) return;

            console.log('🢄SimplePhotoWorker: Sending config update with sources...');
            
            this.sendMessage('configUpdated', {
                config: {
                    expectedWorkerVersion: __WORKER_VERSION__,
                    sources: sourceList
                }
            });
            
            // Also trigger area update after config to ensure streaming sources load with current bounds
            const currentSpatial = get(spatialState);
            if (currentSpatial.bounds) {
                console.log('🢄SimplePhotoWorker: Sending area update after config to trigger streaming sources...');
                this.sendMessage('areaUpdated', {
                    area: currentSpatial.bounds,
                    range: currentSpatial.range
                });
            }
        });
    }

    private sendMessage(type: string, data?: any): void {
        if (!this.worker) {
            throw new Error('Worker not initialized');
        }

        const frontendMessageId = `frontend_${++this.frontendMessageId}`;
        this.worker.postMessage({frontendMessageId, type, data});
    }


    // All worker communication is now fire-and-forget via config and area updates

    terminate(): void {
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
            this.isInitialized = false;
            this.lastBounds = null;
        }
    }

    isReady(): boolean {
        return this.isInitialized && this.worker !== null;
    }

    // Cache removal methods for hidden content
    removePhotoFromCache(photoId: string, photoSource: string): void {
        if (!this.isInitialized || !this.worker) {
            console.warn('🢄SimplePhotoWorker: Cannot remove photo from cache - worker not initialized');
            return;
        }

        console.log(`SimplePhotoWorker: Removing photo ${photoId} from ${photoSource} cache...`);
        this.sendMessage('removePhoto', {
            photoId: photoId,
            source: photoSource
        });
    }

    removeUserPhotosFromCache(userId: string, userSource: string): void {
        if (!this.isInitialized || !this.worker) {
            console.warn('🢄SimplePhotoWorker: Cannot remove user photos from cache - worker not initialized');
            return;
        }

        console.log(`SimplePhotoWorker: Removing all photos by user ${userId} from ${userSource} cache...`);
        this.sendMessage('removeUserPhotos', {
            userId: userId,
            source: userSource
        });
    }
}

// Global instance
export const simplePhotoWorker = new SimplePhotoWorker();