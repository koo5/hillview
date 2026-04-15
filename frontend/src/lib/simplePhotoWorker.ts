/*
This module manages the new.worker.ts
*/

import {photosInArea, photosInRange, spatialState, picks, mapReady} from './mapState';
import {sourceLoadingStatus, sources, maxPhotosInArea} from './data.svelte';
import {filters, buildFiltersQueryParam} from './components/filters-modal/filtersStore';
import {get} from 'svelte/store';
import {getCurrentToken} from './auth.svelte';
import {createTokenManager} from './tokenManagerFactory';
import {addAlert} from './alertSystem.svelte';
import type {WorkerToastMessage} from './workerToast';
import {removePlaceholder, placeholderPhotos, embedPlaceholders} from './placeholderInjector';
import {TAURI} from './tauri';
import {KotlinPhotoWorker} from './KotlinPhotoWorker';
import type {WorkerConfigData} from './photoWorkerTypes';
import {tick} from 'svelte';

const doLog = false;
const TAG = '🢄SPW: '

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
                if (doLog) console.log(TAG+'Initializing Kotlin photo worker for Tauri');
                // Use Kotlin PhotoWorkerService via Tauri
                this.kotlinWorker = new KotlinPhotoWorker();
                await this.kotlinWorker.initialize();
                this.setupKotlinWorkerHandlers();
            } else {
                if (doLog) console.log(TAG+'Initializing Web Worker for browser');
                // Create worker directly
                this.worker = new Worker(
                    new URL('../webworkers/new.worker.ts', import.meta.url),
                    {type: 'module'}
                );
                this.setupWorkerHandlers();
            }

            // Initialize worker with config update including version check
            const initConfig: WorkerConfigData = {
                sources: get(sources),
                queryOptionsJson: buildFiltersQueryParam(),
                maxPhotosInArea: get(maxPhotosInArea)
            };
            this.sendMessage('configUpdated', { config: initConfig });
            this.isInitialized = true;

            // Set up reactive subscriptions
            this.setupReactivity();

            // Test: Check initial sources
            //const initialSources = get(sources);
            /*if (doLog) console.log(TAG+'Initial sources on startup:', JSON.stringify(
            initialSources.map(s => ({
                id: s.id,
                type: s.type,
                enabled: s.enabled,
                url: s.url,
                keys: Object.keys(s),
                JSON: JSON.stringify(s)
            }))));*/

        } catch (error) {
            console.error(TAG+'Failed to initialize', error);
            throw error;
        }
    }

    private setupKotlinWorkerHandlers(): void {
        if (!this.kotlinWorker) return;

        this.kotlinWorker.onmessage = (e: { data: any }) => {
            const message = e.data;
            //if (doLog) console.log(TAG+'Received message from Kotlin worker:', message.type);
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
            console.error(TAG+'Worker error', error);
        };
    }

    private handleWorkerUpdate(message: any): void {
        switch (message.type) {
            case 'photosUpdate':

                const areaPhotos = message.photos_in_area || [];
                const rangePhotos = message.photos_in_range || [];

                // Clean up placeholders that match device photos
                const devicePhotoIds = areaPhotos.filter((p: any) => p.is_device_photo).map((p: any) => p.id);
                if (devicePhotoIds.length > 0) {
                    this.handlePlaceholderCleanup(devicePhotoIds);
                }

                // Merge placeholders with worker photos for immediate display (only if device source is enabled)
                const currentPlaceholders = get(placeholderPhotos);
                const deviceSourceEnabled = this.isDeviceSourceEnabled();
                const filteredPlaceholders = deviceSourceEnabled ? currentPlaceholders : [];

				const spatial = get(spatialState);
				const withPlaceholders = embedPlaceholders(areaPhotos, rangePhotos, filteredPlaceholders, spatial.bounds, spatial.center, spatial.range);

                const mergedAreaPhotos = withPlaceholders.photos_in_area;
                const mergedRangePhotos = withPlaceholders.photos_in_range;

                //if (doLog) console.log(TAG+`Updated photos - Area: ${areaPhotos.length} + ${filteredPlaceholders.length}/${currentPlaceholders.length} placeholders (device source ${deviceSourceEnabled ? 'enabled' : 'disabled'}) = ${mergedAreaPhotos.length}, Range: ${message.current_range}m, rangePhotos.length: ${rangePhotos.length} + ${filteredPlaceholders.length} placeholders = ${mergedRangePhotos.length}`);

                photosInArea.set(mergedAreaPhotos);
                photosInRange.set(mergedRangePhotos);
                break;

            case 'sourceLoadingStatus':
                sourceLoadingStatus.update(status => ({
                    ...status,
                    [message.source_id]: {
                        is_loading: message.is_loading,
                        progress: message.progress,
                        error: message.error
                    }
                }));
                break;

            case 'error':
                console.error(TAG+'Worker error', message.error);
                break;

            case 'toast':
                const toastMessage = message as WorkerToastMessage;
                console.log(TAG+`Received toast from worker: ${toastMessage.level} - ${toastMessage.message} (source: ${toastMessage.source})`);

                // Convert worker toast to main thread toast
                const duration = toastMessage.duration !== undefined ? toastMessage.duration :
                    (toastMessage.level === 'error' ? 0 : 5000); // Persistent errors, auto-dismiss others

                addAlert(toastMessage.message, toastMessage.level, { duration, source: toastMessage.source });
                break;

            case 'getAuthToken':
                this.handleAuthTokenRequest(message.forceRefresh);
                break;

            default:
                console.warn(TAG+'Unknown message type:', message.type);
        }
    }

    private async handleAuthTokenRequest(forceRefresh: boolean = false): Promise<void> {
        try {
            // Use the token manager to get a token with optional force refresh
            const tokenManager = createTokenManager();
            const currentToken = await tokenManager.getValidToken(forceRefresh);
            console.log(TAG+`Sending auth token to worker: ${currentToken ? 'token available' : 'no token'}${forceRefresh ? ' (refreshed)' : ''}`);

            this.worker?.postMessage({
                type: 'authToken',
                token: currentToken
            });
        } catch (error) {
            console.error(TAG+'Error getting auth token for worker:', error);
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
                if (doLog) console.log(`🢄📍 Removed placeholder ${placeholder.id} - matching device photo found`);
            }
        }

        if (removedCount > 0) {
            if (doLog) console.log(TAG+`Cleaned up ${removedCount} placeholder(s) after device photos loaded`);
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

		/*if (doLog) console.log('SimplePhotoWorker: Bounds change differences:', {
		oldHeight, oldWidth, latThreshold, lngThreshold, topLeftLatDiff, topLeftLngDiff, bottomRightLatDiff, bottomRightLngDiff,
		topLeftWithinThreshold, bottomRightWithinThreshold
		});*/

        // Return 0 if both corners are within threshold (no significant change), 1 otherwise
        const result = !(topLeftWithinThreshold && bottomRightWithinThreshold);
		//if (doLog) console.log('SimplePhotoWorker: Bounds change significant:', result);
		return result;
    }

    private setupReactivity(): void {
		picks.subscribe((picksSet) => {
			if (!this.isInitialized) return;
			// Notify worker of pick changes (convert Set to Array for serialization)
			//if (doLog) console.log(TAG+'Picks updated, sending to worker...', Array.from(picksSet));
			this.sendMessage('picksUpdated', {
				picks: Array.from(picksSet)
			});
		});
        // Guaranteed first area load when afterInit() signals readiness.
        // Handles the case where spatialState doesn't change from localStorage
        // (same window size, same position) so the subscription below wouldn't fire.
        mapReady.subscribe((ready) => {
            if (!this.isInitialized) return;
            if (!ready) return;
            const spatial = get(spatialState);
            if (!spatial.bounds) return;
            this.lastBounds = spatial.bounds;
            this.sendMessage('areaUpdated', {
                area: spatial.bounds,
                range: spatial.range
            });
        });

        // React to spatial changes - triggers area updates with hysteresis
        spatialState.subscribe(async (spatial) => {
            if (!this.isInitialized) return;
            if (!get(mapReady)) return;

            // Reset lastBounds when bounds become null (e.g., map unmounted)
            // so next bounds update is treated as fresh
            if (!spatial.bounds) {
                this.lastBounds = null;
                return;
            }

            // Skip update if bounds haven't changed significantly (hysteresis)
			// TODO: we could skip area load, but we can't skip range filter
            if (this.lastBounds && !this.boundsChangeSignificant(this.lastBounds, spatial.bounds)) {
                //if (doLog) console.log(TAG+'Skipping area update - bounds change too small');
                return;
            }

            //if (doLog) console.log(TAG+`Sending area update with range ${spatial.range}m...`);
            this.lastBounds = spatial.bounds;
			await tick(); // Ensure any pending picks updates are processed before area
			//console.log('picks at time of areaUpdate trigger:', get(picks));
            this.sendMessage('areaUpdated', {
                area: spatial.bounds,
                range: spatial.range
            });
        });

        // React to source config changes (filter out loading status changes)
        let lastConfigHash = '';
        let lastFiltersHash = '';
        const sendConfigUpdate = () => {
            if (!this.isInitialized) return;

            const sourceList = get(sources);
            const currentFilters = get(filters);
            const currentMaxPhotos = get(maxPhotosInArea);
            const filtersHash = JSON.stringify(currentFilters);

            // Create hash of config-relevant fields only (ignore loading states)
            const configHash = JSON.stringify({
                sources: sourceList.map(source => ({
                    id: source.id,
                    name: source.name,
                    type: source.type,
                    enabled: source.enabled,
                    url: source.url,
                    path: source.path,
                    subtype: source.subtype,
                    clientId: source.client_id,
                    backendUrl: source.backend_url
                })),
                queryOptions: currentFilters,
                maxPhotosInArea: currentMaxPhotos
            });

            // Only trigger config update if actual config changed (not loading states)
            if (configHash === lastConfigHash) {
                //if (doLog) console.log(TAG+'Ignoring config change - no relevant changes');
                return;
            }

            // Clear picks when filters change (not on initial load or source-only changes)
            if (lastFiltersHash !== '' && filtersHash !== lastFiltersHash) {
                if (doLog) console.log(TAG+'Filters changed, clearing picks');
                picks.set(new Set());
                // Send picksUpdated synchronously BEFORE configUpdated
                // (picks.subscribe runs async, so we must send manually here)
                this.sendMessage('picksUpdated', { picks: [] });
            }
            lastFiltersHash = filtersHash;

            lastConfigHash = configHash;
            if (doLog) console.log(TAG+'Sending config update with sources and queryOptions...');

            const config: WorkerConfigData = {
                sources: sourceList,
                queryOptionsJson: buildFiltersQueryParam(),
                maxPhotosInArea: currentMaxPhotos
            };
            this.sendMessage('configUpdated', { config });
        };

        sources.subscribe(() => sendConfigUpdate());
        filters.subscribe(() => sendConfigUpdate());
        maxPhotosInArea.subscribe(() => sendConfigUpdate());
    }

    private sendMessage(type: string, data?: any): void {
        const frontendMessageId = `frontend_${++this.frontendMessageId}`;
        const message = {frontendMessageId, type, data};

        if (doLog) console.log(TAG+`[${frontendMessageId}] Sending ${type} to worker`);

        if (this.kotlinWorker) {
            this.kotlinWorker.postMessage(message);
        } else if (this.worker) {
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

    /**
     * Abort all running area processes in the worker.
     * Call when navigating away from the map to prevent stale results
     * from a previous location overwriting fresh data.
     */
    abortAreaProcesses(): void {
        if (!this.isInitialized || (!this.worker && !this.kotlinWorker)) return;
        if (doLog) console.log(TAG+'Aborting area processes');
        this.sendMessage('abortArea', {});
    }

    // Cache removal methods for hidden content
    removePhotoFromCache(photoId: string, photoSource: string): void {
        if (!this.isInitialized || (!this.worker && !this.kotlinWorker)) {
            console.warn(TAG+'Cannot remove photo from cache - worker not initialized');
            return;
        }

        if (doLog) console.log(TAG+`Removing photo ${photoId} from ${photoSource} cache...`);
        this.sendMessage('removePhoto', {
            photoId: photoId,
            source: photoSource
        });
    }

    removeUserPhotosFromCache(userId: string, userSource: string): void {
        if (!this.isInitialized || (!this.worker && !this.kotlinWorker)) {
            console.warn(TAG+'Cannot remove user photos from cache - worker not initialized');
            return;
        }

        if (doLog) console.log(TAG+`Removing all photos by user ${userId} from ${userSource} cache...`);
        this.sendMessage('removeUserPhotos', {
            userId: userId,
            source: userSource
        });
    }
}

// Global instance
export const simplePhotoWorker = new SimplePhotoWorker();
