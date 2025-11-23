// Network worker manager for tile fallback functionality
import { currentTileProvider, getProviderConfig, type ProviderName } from './tileProviders';

class NetworkWorkerManager {
    private registration: ServiceWorkerRegistration | null = null;
    private isInitialized = false;

    async init(): Promise<void> {
        if (this.isInitialized || typeof window === 'undefined' || !('serviceWorker' in navigator)) {
            return;
        }

        try {
            console.log('Registering network service worker...');

            this.registration = await navigator.serviceWorker.register('/network-worker.js', {
                scope: '/',
            });

            console.log('Network service worker registered successfully');

            // Listen for messages from service worker
            navigator.serviceWorker.addEventListener('message', (event) => {
                this.handleWorkerMessage(event.data);
            });

            // Wait for worker to be ready
            await navigator.serviceWorker.ready;
            this.isInitialized = true;
            console.log('Network service worker ready');

            // Subscribe to provider changes
            this.subscribeToProviderChanges();

        } catch (error) {
            console.error('Failed to register network service worker:', error);
        }
    }

    private subscribeToProviderChanges(): void {
        currentTileProvider.subscribe((providerName) => {
            this.updateTileProvider(providerName);
        });
    }

    private updateTileProvider(providerName: ProviderName): void {
        if (!this.isInitialized || !this.registration?.active) {
            console.log('Network worker not ready, skipping provider update');
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

        this.registration.active.postMessage(message);
        console.log('Sent tile provider update to network worker:', providerName);
    }

    private handleWorkerMessage(data: any): void {
        if (data.type === 'ERROR') {
            console.error('Network worker error:', {
                error: data.error,
                context: data.context,
                timestamp: new Date(data.timestamp).toISOString()
            });
        }
    }

    isReady(): boolean {
        return this.isInitialized && !!(this.registration?.active);
    }
}

export const networkWorkerManager = new NetworkWorkerManager();