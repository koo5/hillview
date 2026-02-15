// Shared auth and config storage for browser
// Used by both main app and service worker

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

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };

            request.onupgradeneeded = (event) => {
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

    async saveBackendUrl(url: string): Promise<void> {
        await this.open();

        const transaction = this.db!.transaction([CONFIG_STORE], 'readwrite');
        const store = transaction.objectStore(CONFIG_STORE);

        return new Promise((resolve, reject) => {
            const request = store.put(url, 'backendUrl');
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async getBackendUrl(): Promise<string> {
        await this.open();

        const transaction = this.db!.transaction([CONFIG_STORE], 'readonly');
        const store = transaction.objectStore(CONFIG_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get('backendUrl');
            request.onsuccess = () => {
                // Default to localhost if not set
                resolve(request.result || 'http://localhost:8055/api');
            };
            request.onerror = () => reject(request.error);
        });
    }
}

export const authStorage = new AuthStorage();