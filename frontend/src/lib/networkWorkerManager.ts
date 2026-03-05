// Network worker manager for tile fallback functionality
// Communicates with SvelteKit's service worker (src/service-worker.ts)
// which handles tile fetch interception via $lib/sw/tileHandler.ts
import { currentTileProvider, getProviderConfig, type ProviderName } from './tileProviders';
import { initSyncStatusListener } from './syncStatus';

class NetworkWorkerManager {
    private isInitialized = false;

    async init(): Promise<void> {
        if (this.isInitialized || typeof window === 'undefined' || !('serviceWorker' in navigator)) {
            return;
        }

        try {
            console.log('Waiting for service worker to be ready...');

            // Wait for SvelteKit's auto-registered service worker
            await navigator.serviceWorker.ready;

            // Listen for messages from service worker
            navigator.serviceWorker.addEventListener('message', (event) => {
                this.handleWorkerMessage(event.data);
            });

            // Set up sync status listener early so SW health-check
            // messages are captured as soon as they arrive.
            initSyncStatusListener();

            this.isInitialized = true;
            console.log('Service worker ready for tile handling');

            // Subscribe to provider changes
            this.subscribeToProviderChanges();

        } catch (error) {
            console.error('Failed to initialize service worker communication:', error);
        }
    }

    private subscribeToProviderChanges(): void {
        currentTileProvider.subscribe((providerName) => {
            this.updateTileProvider(providerName);
        });
    }

    private updateTileProvider(providerName: ProviderName): void {
        if (!this.isInitialized) {
            console.log('Service worker not ready, skipping provider update');
            return;
        }

        const controller = navigator.serviceWorker.controller;
        if (!controller) {
            console.log('No active service worker controller, skipping provider update');
            return;
        }

        const config = getProviderConfig(providerName);

        const message = {
            type: 'SET_TILE_PROVIDER',
            data: {
                name: providerName,
                url: config.url,
                subdomains: config.subdomains
            }
        };

        controller.postMessage(message);
        console.log('Sent tile provider update to service worker:', providerName);
    }

    private handleWorkerMessage(data: any): void {
        if (data.type === 'ERROR') {
            console.error('Service worker error:', {
                error: data.error,
                context: data.context,
                timestamp: new Date(data.timestamp).toISOString()
            });
        }
    }

    isReady(): boolean {
        return this.isInitialized && !!navigator.serviceWorker.controller;
    }
}

export const networkWorkerManager = new NetworkWorkerManager();
