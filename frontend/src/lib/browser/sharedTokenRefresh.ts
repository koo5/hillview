/**
 * Shared token refresh logic for browser environments
 * Used by both main thread (webTokenManager) and service worker
 * Implements locking via IndexedDB to prevent race conditions
 */

import { backendUrl as configBackendUrl } from '$lib/config';
import { authStorage, type IndexedDbTokenData } from './authStorage';

const DB_NAME = 'HillviewAuthDB';
const AUTH_STORE = 'auth';

export class SharedTokenRefresh {
    private readonly LOG_PREFIX: string;
    private refreshPromise: Promise<boolean> | null = null;
    private readonly LOCK_TIMEOUT_MS = 60000; // 60 seconds

    constructor(logPrefix: string = '[SharedTokenRefresh]') {
        this.LOG_PREFIX = logPrefix;
    }

    async getValidToken(forceRefresh: boolean = false): Promise<string | null> {
        // If refresh is already in progress in this context, wait for it
        if (this.refreshPromise && !forceRefresh) {
            console.log(`${this.LOG_PREFIX} Refresh in progress (local), waiting...`);
            const success = await this.refreshPromise;
            if (success) {
                const tokenData = await this.getStoredTokenData();
                return tokenData?.access_token || null;
            }
            return null;
        }

        const tokenData = await this.getStoredTokenData();
        if (!tokenData) {
            console.log(`${this.LOG_PREFIX} No token stored`);
            return null;
        }

        const now = Date.now();
        const tokenExpired = tokenData.expires_at <= now;
        const needsRefresh = forceRefresh || tokenExpired;

        if (needsRefresh) {
            console.log(`${this.LOG_PREFIX} Token ${forceRefresh ? 'force refresh' : 'expired'}, attempting refresh...`);

            // Try to refresh with locking
            this.refreshPromise = this.refreshWithLock(tokenData.refresh_token);
            const success = await this.refreshPromise;
            this.refreshPromise = null;

            if (success) {
                const newTokenData = await this.getStoredTokenData();
                return newTokenData?.access_token || null;
            }
            return null;
        }

        return tokenData.access_token;
    }

    private async refreshWithLock(refreshToken: string): Promise<boolean> {
        const lockId = `refresh-${Date.now()}-${Math.random()}`;

        try {
            // Try to acquire lock
            const lockAcquired = await this.tryAcquireLock(lockId);

            if (!lockAcquired) {
                console.log(`${this.LOG_PREFIX} Could not acquire lock, waiting for other refresh...`);

                // Wait for the other refresh to complete
                let attempts = 0;
                const now = Date.now();
                const maxWaitTime = this.LOCK_TIMEOUT_MS + 10000; // Lock timeout + 10s buffer
                const checkInterval = 500; // Check every 500ms
                const maxAttempts = Math.ceil(maxWaitTime / checkInterval);

                while (attempts < maxAttempts) {
                    await new Promise(resolve => setTimeout(resolve, checkInterval));

                    // Check if token was refreshed
                    const tokenData = await this.getStoredTokenData();
                    if (tokenData && tokenData.expires_at > now) {
                        console.log(`${this.LOG_PREFIX} Token refreshed by other context`);
                        return true;
                    }

                    // Check if lock was released or expired
                    const lock = await this.getLock();
                    if (!lock || lock.locked_at < now - this.LOCK_TIMEOUT_MS) {
                        console.log(`${this.LOG_PREFIX} Lock expired (older than ${this.LOCK_TIMEOUT_MS}ms), retrying...`);
                        return this.refreshWithLock(refreshToken);
                    }

                    attempts++;
                }

                console.log(`${this.LOG_PREFIX} Timeout waiting for refresh`);
                return false;
            }

            // We have the lock, perform refresh
            console.log(`${this.LOG_PREFIX} Lock acquired, performing refresh...`);

            // Double-check token wasn't refreshed while acquiring lock
            const now = Date.now();
            const currentTokenData = await this.getStoredTokenData();
            if (currentTokenData && currentTokenData.expires_at > now) {
                console.log(`${this.LOG_PREFIX} Token was refreshed while acquiring lock`);
                await this.releaseLock(lockId);
                return true;
            }

            // Perform the actual refresh
            const success = await this.performRefresh(refreshToken);

            // Release lock
            await this.releaseLock(lockId);

            return success;

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Refresh with lock failed:`, error);
            await this.releaseLock(lockId);
            return false;
        }
    }

    private async performRefresh(refreshToken: string): Promise<boolean> {
        try {
            if (!refreshToken) {
                console.log(`${this.LOG_PREFIX} No refresh token available`);
                return false;
            }

            // Use backend URL from config
            const backendUrl = configBackendUrl;

            const response = await fetch(`${backendUrl}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    refresh_token: refreshToken
                })
            });

            if (!response.ok) {
                console.error(`${this.LOG_PREFIX} Refresh failed: ${response.status} ${response.statusText}`);
                if (response.status === 401 || response.status === 403) {
                    // Refresh token is invalid
                    await this.clearTokenData();
                }
                return false;
            }

            const tokenData = await response.json();
            console.log(`${this.LOG_PREFIX} Token refresh successful`);

            // Store new tokens (converting dates to timestamps)
            await this.storeTokenData({
                access_token: tokenData.access_token,
                refresh_token: tokenData.refresh_token,
                expires_at: new Date(tokenData.expires_at).getTime(),
                refresh_token_expires: tokenData.refresh_token_expires_at
                    ? new Date(tokenData.refresh_token_expires_at).getTime()
                    : undefined
            });

            return true;
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to refresh token:`, error);
            return false;
        }
    }

    private async tryAcquireLock(lockId: string): Promise<boolean> {
        try {
            const db = await this.openDB();
            const transaction = db.transaction([AUTH_STORE], 'readwrite');
            const store = transaction.objectStore(AUTH_STORE);

            // Check if lock exists
            const existingLock = await new Promise<any>((resolve) => {
                const request = store.get('refresh_lock');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => resolve(null);
            });

            const now = Date.now();

            // If lock exists and is recent, we can't acquire it
            if (existingLock && existingLock.locked_at > now - this.LOCK_TIMEOUT_MS) {
                console.log(`${this.LOG_PREFIX} Lock already held by ${existingLock.locked_by}`);
                return false;
            }

            // Try to acquire lock
            const lockData = {
                locked_by: lockId,
                locked_at: now
            };

            return new Promise((resolve) => {
                const request = store.put(lockData, 'refresh_lock');
                request.onsuccess = () => {
                    console.log(`${this.LOG_PREFIX} Lock acquired: ${lockId}`);
                    resolve(true);
                };
                request.onerror = () => resolve(false);
            });
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to acquire lock:`, error);
            return false;
        }
    }

    private async releaseLock(lockId: string): Promise<void> {
        try {
            const db = await this.openDB();
            const transaction = db.transaction([AUTH_STORE], 'readwrite');
            const store = transaction.objectStore(AUTH_STORE);

            // Only release if we own the lock
            const existingLock = await new Promise<any>((resolve) => {
                const request = store.get('refresh_lock');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => resolve(null);
            });

            if (existingLock && existingLock.locked_by === lockId) {
                await new Promise((resolve, reject) => {
                    const request = store.delete('refresh_lock');
                    request.onsuccess = () => {
                        console.log(`${this.LOG_PREFIX} Lock released: ${lockId}`);
                        resolve(undefined);
                    };
                    request.onerror = () => reject(request.error);
                });
            }
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Failed to release lock:`, error);
        }
    }

    private async getLock(): Promise<any> {
        try {
            const db = await this.openDB();
            const transaction = db.transaction([AUTH_STORE], 'readonly');
            const store = transaction.objectStore(AUTH_STORE);

            return new Promise((resolve) => {
                const request = store.get('refresh_lock');
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => resolve(null);
            });
        } catch (error) {
            return null;
        }
    }

    async getStoredTokenData(): Promise<IndexedDbTokenData | null> {
        return authStorage.getTokenData();
    }

    private async storeTokenData(tokenData: IndexedDbTokenData): Promise<void> {
        await authStorage.saveTokenData(tokenData);
        console.log(`${this.LOG_PREFIX} Token data stored`);
    }

    private async clearTokenData(): Promise<void> {
        await authStorage.clearToken();
    }

    private openDB(): Promise<IDBDatabase> {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, 1);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = (event.target as IDBOpenDBRequest).result;

                // Create auth store if needed
                if (!db.objectStoreNames.contains(AUTH_STORE)) {
                    db.createObjectStore(AUTH_STORE);
                }
            };
        });
    }
}