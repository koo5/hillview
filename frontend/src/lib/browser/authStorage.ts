// Shared auth and config storage for browser
// Used by both main app and service worker

import type { TokenData } from './sharedTokenRefresh';

const DB_NAME = 'HillviewPhotoDB';
const DB_VERSION = 2;
const AUTH_STORE = 'auth';
const CONFIG_STORE = 'config';

export interface StoredToken {
    value: string;
    expires_at: number;
}

export interface StoredConfig {
    backendUrl: string;
}

export class AuthStorage {
    private db: IDBDatabase | null = null;

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

                // Photos store (existing)
                if (!db.objectStoreNames.contains('photos')) {
                    const store = db.createObjectStore('photos', { keyPath: 'id' });
                    store.createIndex('uploaded', 'uploaded');
                    store.createIndex('captured_at', 'captured_at');
                    store.createIndex('created_at', 'created_at');
                }

                // Auth store
                if (!db.objectStoreNames.contains(AUTH_STORE)) {
                    db.createObjectStore(AUTH_STORE);
                }

                // Config store
                if (!db.objectStoreNames.contains(CONFIG_STORE)) {
                    db.createObjectStore(CONFIG_STORE);
                }
            };
        });
    }

    async saveToken(token: string, expiresAt: number): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE);

        const tokenData: StoredToken = {
            value: token,
            expires_at: expiresAt
        };

        return new Promise((resolve, reject) => {
            const request = store.put(tokenData, 'token');
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async getToken(): Promise<StoredToken | null> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readonly');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get('token');
            request.onsuccess = () => {
                const token = request.result;
                if (token && token.expires_at > Date.now()) {
                    resolve(token);
                } else {
                    resolve(null);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }

    async clearToken(): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.delete('token');
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    // New methods for full TokenData support
    async saveTokenData(tokenData: TokenData): Promise<void> {
        console.log('[AuthStorage] saveTokenData called');
        await this.open();
        console.log('[AuthStorage] DB opened, creating transaction');

        const transaction = this.db!.transaction([AUTH_STORE], 'readwrite');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            console.log('[AuthStorage] Putting token data...');
            const request = store.put(tokenData, 'token');
            request.onsuccess = () => {
                console.log('[AuthStorage] Token data saved successfully');
                resolve();
            };
            request.onerror = () => {
                console.error('[AuthStorage] Error saving token data:', request.error);
                reject(request.error);
            };

            // Also handle transaction errors
            transaction.onerror = () => {
                console.error('[AuthStorage] Transaction error:', transaction.error);
                reject(transaction.error);
            };
            transaction.oncomplete = () => {
                console.log('[AuthStorage] Transaction completed');
            };
        });
    }

    async getTokenData(): Promise<TokenData | null> {
        await this.open();

        const transaction = this.db!.transaction([AUTH_STORE], 'readonly');
        const store = transaction.objectStore(AUTH_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get('token');
            request.onsuccess = () => {
                const data = request.result;
                if (data && data.access_token) {
                    resolve(data as TokenData);
                } else {
                    resolve(null);
                }
            };
            request.onerror = () => reject(request.error);
        });
    }

}

export const authStorage = new AuthStorage();
