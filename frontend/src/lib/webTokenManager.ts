import type { TokenManager, TokenData } from './tokenManager';
import { TokenExpiredError, TokenRefreshError } from './tokenManager';
import { backendUrl } from './config';
import { auth } from './authStore';
import { logout } from './auth.svelte';
import { clientCrypto } from './clientCrypto';
import { http } from '$lib/http';
import { authStorage, type IndexedDbTokenData } from './browser/authStorage';

/**
 * Web Token Manager
 *
 * Handles token management for web-only environments using IndexedDB.
 * Single source of truth with cross-tab reactivity via BroadcastChannel.
 * Implements race condition protection through promise deduplication.
 */
export class WebTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🔐[WEB_TOKEN_MGR]';
    private refreshPromise: Promise<TokenData> | null = null;

    // Local cache to avoid async reads on every token access
    private cachedTokenData: IndexedDbTokenData | null = null;
    private cacheInitialized = false;

    constructor() {
        // Subscribe to cross-tab auth changes
        authStorage.onAuthChange(async () => {
            console.log(`${this.LOG_PREFIX} Auth changed in another tab, refreshing cache`);
            await this.refreshCache();

            // Update auth store based on new token state
            if (this.cachedTokenData) {
                auth.update(state => ({ ...state, is_authenticated: true }));
            } else {
                auth.update(state => ({ ...state, is_authenticated: false, user: null }));
            }
        });
    }

    // Initialize cache from IndexedDB (call once on app startup)
    async init(): Promise<void> {
        if (this.cacheInitialized) return;
        await this.refreshCache();
        this.cacheInitialized = true;
    }

    private async refreshCache(): Promise<void> {
        this.cachedTokenData = await authStorage.getTokenData();
    }

    private async ensureCacheInitialized(): Promise<void> {
        if (!this.cacheInitialized) {
            await this.init();
        }
    }

    async getValidToken(force: boolean = false): Promise<string | null> {
        try {
            await this.ensureCacheInitialized();

            // If refresh is already in progress, wait for it
            if (this.refreshPromise) {
                console.log(`${this.LOG_PREFIX} Refresh in progress, waiting...`);
                try {
                    const newToken = await this.refreshPromise;
                    return newToken.access_token;
                } catch (error) {
                    console.error(`${this.LOG_PREFIX} Refresh failed:`, error);
                    return null;
                }
            }

            if (!this.cachedTokenData) {
                console.log(`${this.LOG_PREFIX} No token available`);
                return null;
            }

            // Check if token is expired OR refresh token needs proactive renewal OR force refresh
            const tokenExpired = await this.isTokenExpired();
            const needsRefreshRenewal = await this.shouldRenewRefreshToken();

            if (force || tokenExpired || needsRefreshRenewal) {
                if (force) {
                    console.log(`${this.LOG_PREFIX} Force refresh requested (e.g., after 401)`);
                } else if (tokenExpired) {
                    console.log(`${this.LOG_PREFIX} Token expired, attempting refresh`);
                } else {
                    console.log(`${this.LOG_PREFIX} Refresh token expiring soon, proactive renewal`);
                }

                this.refreshPromise = this.performRefresh();

                try {
                    const newToken = await this.refreshPromise;
                    this.refreshPromise = null;
                    return newToken.access_token;
                } catch (error) {
                    this.refreshPromise = null;
                    console.error(`${this.LOG_PREFIX} Refresh failed:`, error);
                    logout('Token refresh failed');
                    throw new TokenExpiredError('Token expired and refresh failed');
                }
            }

            return this.cachedTokenData.access_token;

        } catch (error) {
            if (error instanceof TokenExpiredError) {
                throw error;
            }
            console.error(`${this.LOG_PREFIX} Error getting valid token:`, error);
            return null;
        }
    }

    async refreshToken(): Promise<boolean> {
        try {
            console.log(`${this.LOG_PREFIX} Manual token refresh requested`);

            if (this.refreshPromise) {
                console.log(`${this.LOG_PREFIX} Refresh already in progress, waiting...`);
                await this.refreshPromise;
                return true;
            }

            this.refreshPromise = this.performRefresh();
            await this.refreshPromise;
            this.refreshPromise = null;

            return true;

        } catch (error) {
            this.refreshPromise = null;
            console.error(`${this.LOG_PREFIX} Manual refresh failed:`, error);
            return false;
        }
    }

    private async performRefresh(attempt: number = 1, maxAttempts: number = 3): Promise<TokenData> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.refresh_token) {
            throw new TokenRefreshError('No refresh token available');
        }

        const refreshToken = this.cachedTokenData.refresh_token;
        const refreshExpires = this.cachedTokenData.refresh_token_expires;

        if (!refreshExpires) {
            throw new TokenRefreshError('No refresh token expiry stored');
        }

        // Check if refresh token is expired
        const now = Date.now();
        const bufferTime = 1 * 60 * 1000; // 1 minute buffer

        if (now + bufferTime >= refreshExpires) {
            console.warn(`${this.LOG_PREFIX} Refresh token expired`);
            throw new TokenRefreshError('Refresh token expired');
        }

        const hoursRemaining = Math.round((refreshExpires - now) / (1000 * 60 * 60));
        console.log(`${this.LOG_PREFIX} Refresh token valid (${hoursRemaining} hours remaining)`);

        const refreshStartTime = Date.now();
        console.log(`${this.LOG_PREFIX} Performing token renewal (attempt ${attempt}/${maxAttempts})`);

        // Update auth store with refresh status
        auth.update(state => ({
            ...state,
            refresh_status: attempt === 1 ? 'refreshing' : 'retrying',
            refresh_attempt: attempt
        }));

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);

            const response = await fetch(`${backendUrl}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            const refreshDuration = Date.now() - refreshStartTime;
            console.log(`${this.LOG_PREFIX} Refresh completed in ${refreshDuration}ms, status: ${response.status}`);

            if (!response.ok) {
                const errorText = await response.text();
                let errorDetail;
                try {
                    const errorJson = JSON.parse(errorText);
                    errorDetail = errorJson.detail || errorJson.message || errorText;
                } catch {
                    errorDetail = errorText;
                }
                console.error(`${this.LOG_PREFIX} Refresh failed: ${response.status} ${errorDetail}`);

                if (response.status === 401 || response.status === 403) {
                    throw new TokenRefreshError(`Refresh failed: ${errorDetail}`);
                }
                throw new Error(`HTTP ${response.status}: ${errorDetail}`);
            }

            const tokenData = await response.json() as TokenData;
            await this.storeTokens(tokenData);

            console.log(`${this.LOG_PREFIX} Token refresh successful`);

            auth.update(state => ({
                ...state,
                refresh_status: 'idle',
                refresh_attempt: undefined
            }));

            return tokenData;

        } catch (error) {
            const refreshDuration = Date.now() - refreshStartTime;

            if (error instanceof TokenRefreshError) {
                console.error(`${this.LOG_PREFIX} Token refresh failed permanently after ${refreshDuration}ms`);
                throw error;
            }

            const isTimeout = error instanceof Error && error.name === 'AbortError';
            const isNetworkError = error instanceof TypeError && error.message.includes('fetch');
            const errorMessage = error instanceof Error ? error.message : String(error);

            console.warn(`${this.LOG_PREFIX} Refresh attempt ${attempt} failed:`,
                isTimeout ? 'timeout' : isNetworkError ? 'network error' : errorMessage);

            if (attempt < maxAttempts && (isTimeout || isNetworkError || errorMessage.includes('HTTP 5'))) {
                const delayMs = Math.pow(2, attempt - 1) * 1000;
                console.log(`${this.LOG_PREFIX} Retrying in ${delayMs}ms...`);
                await new Promise(resolve => setTimeout(resolve, delayMs));
                return this.performRefresh(attempt + 1, maxAttempts);
            }

            console.error(`${this.LOG_PREFIX} Token refresh failed after ${attempt} attempts`);

            auth.update(state => ({
                ...state,
                refresh_status: 'failed',
                refresh_attempt: attempt
            }));

            throw new TokenRefreshError(`Refresh failed after ${attempt} attempts: ${errorMessage}`);
        }
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
        if (tokenData.refresh_token && !tokenData.refresh_token_expires_at) {
            throw new Error('Refresh token provided without expiry date');
        }

        // Convert API format (string dates) to IndexedDB format (number timestamps)
        const indexedDbData: IndexedDbTokenData = {
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token || this.cachedTokenData?.refresh_token || '',
            expires_at: new Date(tokenData.expires_at).getTime(),
            refresh_token_expires: tokenData.refresh_token_expires_at
                ? new Date(tokenData.refresh_token_expires_at).getTime()
                : this.cachedTokenData?.refresh_token_expires
        };

        await authStorage.saveTokenData(indexedDbData);

        // Update local cache
        this.cachedTokenData = indexedDbData;

        console.log(`${this.LOG_PREFIX} Tokens stored in IndexedDB`);

        auth.update(state => ({ ...state, is_authenticated: true }));
    }

    async registerClientPublicKey(): Promise<void> {
        console.log(`${this.LOG_PREFIX} Registering client public key`);

        const keyInfo = await clientCrypto.getPublicKeyInfo();

        const response = await http.post('/auth/register-client-key', {
            public_key_pem: keyInfo.public_key_pem,
            key_id: keyInfo.key_id,
            created_at: keyInfo.created_at
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(`Registration failed: ${error.detail || response.statusText}`);
        }

        console.log(`${this.LOG_PREFIX} Client public key registered`);
    }

    async clearTokens(): Promise<void> {
        console.log(`${this.LOG_PREFIX} Clearing tokens`);

        await authStorage.clearToken();
        this.cachedTokenData = null;

        console.log(`${this.LOG_PREFIX} Tokens cleared from IndexedDB`);

        auth.update(state => ({
            ...state,
            is_authenticated: false,
            user: null
        }));
    }

    async isTokenExpired(bufferMinutes: number = 2): Promise<boolean> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.expires_at) {
            return true;
        }

        const now = Date.now();
        const bufferMs = bufferMinutes * 60 * 1000;
        return (this.cachedTokenData.expires_at - bufferMs) <= now;
    }

    private async shouldRenewRefreshToken(bufferDays: number = 3): Promise<boolean> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.refresh_token_expires) {
            return false; // No refresh token expiry, can't determine
        }

        const now = Date.now();
        const bufferMs = bufferDays * 24 * 60 * 60 * 1000;
        return now + bufferMs >= this.cachedTokenData.refresh_token_expires;
    }
}
