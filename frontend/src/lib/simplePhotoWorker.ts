import {photosInArea, photosInRange, spatialState} from './mapState';
import {sourceLoadingStatus, sources} from './data.svelte';
import {get} from 'svelte/store';
import {getCurrentToken} from './auth.svelte';
import {createTokenManager} from './tokenManagerFactory';
import {addAlert} from './alertSystem.svelte';
import type {WorkerToastMessage} from './workerToast';
import {removePlaceholder, placeholderPhotos, embedPlaceholders} from './placeholderInjector';
import {TAURI} from './tauri';
import {KotlinPhotoWorker} from './KotlinPhotoWorker';

declare const __WORKER_VERSION__: string;


class SimplePhotoWorker {
    private worker: Worker | null = null;
    private kotlinWorker: KotlinPhotoWorker | null = null;
    private frontendMessageId = 0;
    private isInitialized = false;
    private lastBounds: any = null;

    async initialize(): Promise<void> {
        if ((this.worker || this.kotlinWorker) && this.isInitialized) return;

        try {
            if (TAURI) {
                console.log('🢄SimplePhotoWorker: Initializing Kotlin photo worker for Tauri');
                // Use Kotlin PhotoWorkerService via Tauri
                this.kotlinWorker = new KotlinPhotoWorker();
                await this.kotlinWorker.initialize();
                this.setupKotlinWorkerHandlers();
            } else {
                console.log('🢄SimplePhotoWorker: Initializing Web Worker for browser');
                // Create worker directly
                this.worker = new Worker(
                    new URL('./new.worker.ts', import.meta.url),
                    {type: 'module'}
                );
                this.setupWorkerHandlers();
            }

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
            /*console.log('🢄SimplePhotoWorker: Initial sources on startup:', JSON.stringify(
            initialSources.map(s => ({
                id: s.id,
                type: s.type,
                enabled: s.enabled,
                url: s.url,
                keys: Object.keys(s),
                JSON: JSON.stringify(s)
            }))));*/

        } catch (error) {
            console.error('🢄SimplePhotoWorker: Failed to initialize', error);
            throw error;
        }
    }

    private setupKotlinWorkerHandlers(): void {
        if (!this.kotlinWorker) return;

        this.kotlinWorker.onmessage = (e: { data: any }) => {
            const message = e.data;
            console.log('🢄SimplePhotoWorker: Received message from Kotlin worker:', message.type);
            this.handleWorkerUpdate(message);
        };
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

                const areaPhotos = message.photosInArea || [];
                const rangePhotos = message.photosInRange || [];

                // Clean up placeholders that match device photos
                const devicePhotoIds = areaPhotos.filter((p: any) => p.isDevicePhoto).map((p: any) => p.id);
                if (devicePhotoIds.length > 0) {
                    this.handlePlaceholderCleanup(devicePhotoIds);
                }

                // Merge placeholders with worker photos for immediate display (only if device source is enabled)
                const currentPlaceholders = get(placeholderPhotos);
                const deviceSourceEnabled = this.isDeviceSourceEnabled();
                const filteredPlaceholders = deviceSourceEnabled ? currentPlaceholders : [];

				const withPlaceholders = embedPlaceholders(areaPhotos, rangePhotos, filteredPlaceholders);

                const mergedAreaPhotos = withPlaceholders.photosInArea;
                const mergedRangePhotos = withPlaceholders.photosInRange;

                console.log(`🢄SimplePhotoWorker: Updated photos - Area: ${areaPhotos.length} + ${filteredPlaceholders.length}/${currentPlaceholders.length} placeholders (device source ${deviceSourceEnabled ? 'enabled' : 'disabled'}) = ${mergedAreaPhotos.length}, Range: ${message.currentRange}m, rangePhotos.length: ${rangePhotos.length} + ${filteredPlaceholders.length} placeholders = ${mergedRangePhotos.length}`);

                photosInArea.set(mergedAreaPhotos);
                photosInRange.set(mergedRangePhotos);
                break;

            case 'sourceLoadingStatus':
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
                const toastMessage = message as WorkerToastMessage;
                console.log(`🢄SimplePhotoWorker: Received toast from worker: ${toastMessage.level} - ${toastMessage.message} (source: ${toastMessage.source})`);

                // Convert worker toast to main thread toast
                const duration = toastMessage.duration !== undefined ? toastMessage.duration :
                    (toastMessage.level === 'error' ? 0 : 5000); // Persistent errors, auto-dismiss others

                addAlert(toastMessage.message, toastMessage.level, { duration, source: toastMessage.source });
                break;

            case 'getAuthToken':
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
            console.log(`🢄SimplePhotoWorker: Sending auth token to worker: ${currentToken ? 'token available' : 'no token'}${forceRefresh ? ' (refreshed)' : ''}`);

            this.worker?.postMessage({
                type: 'authToken',
                token: currentToken
            });
        } catch (error) {
            console.error('🢄SimplePhotoWorker: Error getting auth token for worker:', error);
            this.worker?.postMessage({
                type: 'authToken',
                token: null
            });
        }
    }

    private handlePlaceholderCleanup(devicePhotoIds: string[]): void {
        if (!devicePhotoIds || devicePhotoIds.length === 0) {
            return;
        }

        const currentPlaceholders = get(placeholderPhotos);
        let removedCount = 0;

        // Check each placeholder to see if it matches any device photo ID
        for (const placeholder of currentPlaceholders) {
            if (devicePhotoIds.includes(placeholder.id)) {
                removePlaceholder(placeholder.id);
                removedCount++;
                console.log(`🢄📍 Removed placeholder ${placeholder.id} - matching device photo found`);
            }
        }

        if (removedCount > 0) {
            console.log(`🢄SimplePhotoWorker: Cleaned up ${removedCount} placeholder(s) after device photos loaded`);
        }
    }

    /**
     * Check if the device source is currently enabled
     */
    private isDeviceSourceEnabled(): boolean {
        const currentSources = get(sources);
        const deviceSource = currentSources.find(source => source.id === 'device');
        return deviceSource?.enabled === true;
    }

    private boundsChangeSignificant(oldBounds: any, newBounds: any): boolean {
        // Calculate old area dimensions
        const oldHeight = Math.abs(oldBounds.top_left.lat - oldBounds.bottom_right.lat);
        const oldWidth = Math.abs(oldBounds.bottom_right.lng - oldBounds.top_left.lng);

        const latThreshold = oldHeight * 0.001;
        const lngThreshold = oldWidth * 0.001;

        // Check if both corners are within threshold distances
        const topLeftLatDiff = Math.abs(newBounds.top_left.lat - oldBounds.top_left.lat);
        const topLeftLngDiff = Math.abs(newBounds.top_left.lng - oldBounds.top_left.lng);
        const bottomRightLatDiff = Math.abs(newBounds.bottom_right.lat - oldBounds.bottom_right.lat);
        const bottomRightLngDiff = Math.abs(newBounds.bottom_right.lng - oldBounds.bottom_right.lng);

        const topLeftWithinThreshold = topLeftLatDiff <= latThreshold && topLeftLngDiff <= lngThreshold;
        const bottomRightWithinThreshold = bottomRightLatDiff <= latThreshold && bottomRightLngDiff <= lngThreshold;

		/*console.log('SimplePhotoWorker: Bounds change differences:', {
		oldHeight, oldWidth, latThreshold, lngThreshold, topLeftLatDiff, topLeftLngDiff, bottomRightLatDiff, bottomRightLngDiff,
		topLeftWithinThreshold, bottomRightWithinThreshold
		});*/

        // Return 0 if both corners are within threshold (no significant change), 1 otherwise
        const result = !(topLeftWithinThreshold && bottomRightWithinThreshold);
		//console.log('SimplePhotoWorker: Bounds change significant:', result);
		return result;
    }

    private setupReactivity(): void {
        // React to spatial changes - triggers area updates with hysteresis
        spatialState.subscribe((spatial) => {
            if (!this.isInitialized || !spatial.bounds) return;

            // Skip update if bounds haven't changed significantly (hysteresis)
			// TODO: we could skip area load, but we can't skip range filter
            if (this.lastBounds && !this.boundsChangeSignificant(this.lastBounds, spatial.bounds)) {
                //console.log('🢄SimplePhotoWorker: Skipping area update - bounds change too small');
                return;
            }

            console.log(`🢄SimplePhotoWorker: Sending area update with range ${spatial.range}m...`);
            this.lastBounds = spatial.bounds;
            this.sendMessage('areaUpdated', {
                area: spatial.bounds,
                range: spatial.range
            });
        });

        // React to source config changes (filter out loading status changes)
        let lastConfigHash = '';
        sources.subscribe(async (sourceList) => {
            if (!this.isInitialized) return;

            // Create hash of config-relevant fields only (ignore loading states)
            const configHash = JSON.stringify(sourceList.map(source => ({
                id: source.id,
                name: source.name,
                type: source.type,
                enabled: source.enabled,
                url: source.url,
                path: source.path,
                subtype: source.subtype,
                clientId: source.clientId,
                backendUrl: source.backendUrl
            })));

            // Only trigger config update if actual config changed (not loading states)
            if (configHash === lastConfigHash) {
                //console.log('🢄SimplePhotoWorker: Ignoring source change - only loading states changed');
                return;
            }

            lastConfigHash = configHash;
            //console.log('🢄SimplePhotoWorker: Sending config update with sources...');

            this.sendMessage('configUpdated', {
                config: {
                    expectedWorkerVersion: __WORKER_VERSION__,
                    sources: sourceList
                }
            });
		});
    }

    private sendMessage(type: string, data?: any): void {
        const frontendMessageId = `frontend_${++this.frontendMessageId}`;
        const message = {frontendMessageId, type, data};

        if (this.kotlinWorker) {
            //console.log(`🢄SimplePhotoWorker: Sending message to Kotlin worker: ${type}`);
            this.kotlinWorker.postMessage(message);
        } else if (this.worker) {
            //console.log(`🢄SimplePhotoWorker: Sending message to Web worker: ${type}`);
            this.worker.postMessage(message);
        } else {
            throw new Error('No worker initialized');
        }
    }


    // All worker communication is now fire-and-forget via config and area updates

    terminate(): void {
        if (this.kotlinWorker) {
            this.kotlinWorker.terminate();
            this.kotlinWorker = null;
        }
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
        }
        this.isInitialized = false;
        this.lastBounds = null;
    }

    isReady(): boolean {
        return this.isInitialized && (this.worker !== null || this.kotlinWorker !== null);
    }

    // Cache removal methods for hidden content
    removePhotoFromCache(photoId: string, photoSource: string): void {
        if (!this.isInitialized || (!this.worker && !this.kotlinWorker)) {
            console.warn('🢄SimplePhotoWorker: Cannot remove photo from cache - worker not initialized');
            return;
        }

        console.log(`🢄SimplePhotoWorker: Removing photo ${photoId} from ${photoSource} cache...`);
        this.sendMessage('removePhoto', {
            photoId: photoId,
            source: photoSource
        });
    }

    removeUserPhotosFromCache(userId: string, userSource: string): void {
        if (!this.isInitialized || (!this.worker && !this.kotlinWorker)) {
            console.warn('🢄SimplePhotoWorker: Cannot remove user photos from cache - worker not initialized');
            return;
        }

        console.log(`🢄SimplePhotoWorker: Removing all photos by user ${userId} from ${userSource} cache...`);
        this.sendMessage('removeUserPhotos', {
            userId: userId,
            source: userSource
        });
    }
}

// Global instance
export const simplePhotoWorker = new SimplePhotoWorker();
