// Auth token storage for browser
// Used by both main app and service worker
// Single source of truth for auth tokens in IndexedDB
// Cross-tab reactivity via BroadcastChannel

const DB_NAME = 'HillviewAuthDB';
const DB_VERSION = 1;
const AUTH_STORE = 'auth';
const AUTH_CHANNEL = 'hillview-auth';

// IndexedDB storage format for tokens (number timestamps for easy comparison)
// Different from tokenManager.ts TokenData which uses string dates from API
export interface IndexedDbTokenData {
    access_token: string;
    refresh_token: string;
    expires_at: number;
    refresh_token_expires?: number;
}

// Simple broadcast: "auth state changed, check IndexedDB"
export type AuthBroadcastMessage = { type: 'auth_changed' };

export class AuthStorage {
    private db: IDBDatabase | null = null;
    private channel: BroadcastChannel | null = null;
    private messageHandlers: Set<(msg: AuthBroadcastMessage) => void> = new Set();

    constructor() {
        // BroadcastChannel is not available in service workers in all browsers
        // but is available in main thread
        if (typeof BroadcastChannel !== 'undefined') {
            this.channel = new BroadcastChannel(AUTH_CHANNEL);
            this.channel.onmessage = (event) => {
                const msg = event.data as AuthBroadcastMessage;
                console.log('[AuthStorage] Received broadcast:', msg.type);
                this.messageHandlers.forEach(handler => handler(msg));
            };
        }
    }

    // Subscribe to cross-tab auth changes
    onAuthChange(handler: (msg: AuthBroadcastMessage) => void): () => void {
        this.messageHandlers.add(handler);
        return () => this.messageHandlers.delete(handler);
    }

    private broadcast(message: AuthBroadcastMessage): void {
        if (this.channel) {
            console.log('[AuthStorage] Broadcasting:', message.type);
            this.channel.postMessage(message);
        }
    }

    async open(): Promise<void> {
        if (this.db) return;

        console.log('[AuthStorage] Opening IndexedDB...');
        return new Promise((resolve, reject) => {
            // Timeout to prevent hanging forever if blocked
            const timeout = setTimeout(() => {
                console.error('[AuthStorage] IndexedDB open timed out (likely blocked by another tab)');
                reject(new Error('IndexedDB open timed out - close other tabs and refresh'));
            }, 5000);

            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                clearTimeout(timeout);
                console.error('[AuthStorage] IndexedDB open error:', request.error);
                reject(request.error);
            };
            request.onsuccess = () => {
                clearTimeout(timeout);
                console.log('[AuthStorage] IndexedDB opened successfully');
                this.db = request.result;
                resolve();
            };

            // Handle blocked event - occurs when another connection has the DB open with older version
            request.onblocked = () => {
                clearTimeout(timeout);
                console.warn('[AuthStorage] IndexedDB upgrade blocked - another tab may have the DB open');
                reject(new Error('IndexedDB blocked - close other tabs and refresh'));
            };

            request.onupgradeneeded = (event) => {
                console.log('[AuthStorage] IndexedDB upgrade needed');
                const db = (event.target as IDBOpenDBRequest).result;

                if (!db.objectStoreNames.contains(AUTH_STORE)) {
                    db.createObjectStore(AUTH_STORE);
                }
            };
        });
    }

    async clearToken(): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.delete('token');
            request.onsuccess = () => {
                this.broadcast({ type: 'auth_changed' });
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    async saveTokenData(tokenData: IndexedDbTokenData): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.put(tokenData, 'token');
            request.onsuccess = () => {
                this.broadcast({ type: 'auth_changed' });
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    async getTokenData(): Promise<IndexedDbTokenData | null> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readonly');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get('token');
            request.onsuccess = () => {
                const data = request.result;
                if (data && data.access_token) {
                    resolve(data as IndexedDbTokenData);
                } else {
                    resolve(null);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }

}

export const authStorage = new AuthStorage();
