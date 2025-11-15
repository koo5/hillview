import type { TokenManager, TokenData } from './tokenManager';
import { TokenExpiredError, TokenRefreshError } from './tokenManager';
import { backendUrl } from './config';
import { auth } from './authStore';
import { logout } from './auth.svelte';
import { clientCrypto } from './clientCrypto';
import { http } from '$lib/http';
import { parsePythonDateTime } from './dateUtils';

/**
 * Web Token Manager
 *
 * Handles token management for web-only environments using localStorage.
 * Implements race condition protection through promise deduplication.
 */
export class WebTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🔐[WEB_TOKEN_MGR]';
    private refreshPromise: Promise<TokenData> | null = null;

    async getValidToken(force: boolean = false): Promise<string | null> {
        try {
            //console.log(`${this.LOG_PREFIX} getValidToken...`);

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

            const token = localStorage.getItem('token');
            if (!token) {
                console.log(`${this.LOG_PREFIX} No token to use.`);
                return null;
            }

            // Check if token is expired OR refresh token needs proactive renewal OR force refresh
            const tokenExpired = await this.isTokenExpired();
            const needsRefreshRenewal = await this.shouldRenewRefreshToken();

            if (force || tokenExpired || needsRefreshRenewal) {
                if (force) {
                    console.log(`${this.LOG_PREFIX} Force refresh requested (e.g., after 401), attempting refresh`);
                } else if (tokenExpired) {
                    console.log(`${this.LOG_PREFIX} attempting refresh`);
                } else {
                    console.log(`${this.LOG_PREFIX} Refresh token expiring soon, performing proactive renewal`);
                }

                // Start refresh process
                this.refreshPromise = this.performRefresh();

                try {
                    const newToken = await this.refreshPromise;
                    this.refreshPromise = null;
                    return newToken.access_token;
                } catch (error) {
                    this.refreshPromise = null;
                    console.error(`${this.LOG_PREFIX} Refresh failed:`, error);
                    // Refresh failed means authentication is lost - trigger proper logout
                    logout('Token refresh failed');
                    throw new TokenExpiredError('Token expired and refresh failed');
                }
            }

            //console.log(`${this.LOG_PREFIX} Returning token valid until ${localStorage.getItem('token_expires')}`);
            return token;

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
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            throw new TokenRefreshError('No refresh token available');
        }

        // Check if refresh token is expired
        const refreshExpires = localStorage.getItem('refresh_token_expires');
        if (!refreshExpires) {
            throw new TokenRefreshError('No refresh token expiry stored - invalid token state');
        }

        try {
            const expiryTime = new Date(refreshExpires);
            const now = new Date();
            const bufferTime = 1 * 60 * 1000; // 1 minute buffer

            if (now.getTime() + bufferTime >= expiryTime.getTime()) {
                console.warn(`${this.LOG_PREFIX} Refresh token expired at ${refreshExpires}, current time: ${now.toISOString()}`);
                throw new TokenRefreshError('Refresh token expired');
            }

            console.log(`${this.LOG_PREFIX} Refresh token valid until ${refreshExpires} (${Math.round((expiryTime.getTime() - now.getTime()) / (1000 * 60 * 60))} hours remaining)`);
        } catch (dateError) {
            console.error(`${this.LOG_PREFIX} Could not parse refresh token expiry date: ${refreshExpires}`, dateError);
            throw new TokenRefreshError('Invalid refresh token expiry format');
        }

        const refreshStartTime = Date.now();
        console.log(`${this.LOG_PREFIX} Performing auth token renewal (attempt ${attempt}/${maxAttempts})... (started at ${new Date().toISOString()})`);
        console.debug(`${this.LOG_PREFIX} Refresh token: ${refreshToken.substring(0, 20)}...`);

        // Update auth store with refresh status
        auth.update(state => ({
            ...state,
            refresh_status: attempt === 1 ? 'refreshing' : 'retrying',
            refresh_attempt: attempt
        }));

        try {
            // Create timeout controller for the fetch request
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

            const response = await fetch(`${backendUrl}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    refresh_token: refreshToken
                }),
                signal: controller.signal
            });

            clearTimeout(timeoutId); // Clear timeout on successful response
            const refreshDuration = Date.now() - refreshStartTime;
            console.log(`${this.LOG_PREFIX} Refresh request completed in ${refreshDuration}ms, status: ${response.status}`);

            if (!response.ok) {
                const errorText = await response.text();
                let errorDetail;
                try {
                    const errorJson = JSON.parse(errorText);
                    errorDetail = errorJson.detail || errorJson.message || errorText;
                } catch {
                    errorDetail = errorText;
                }
                console.error(`${this.LOG_PREFIX} Refresh failed - Status: ${response.status}, Error: ${errorDetail}`);

                // For 401/403 errors, don't retry - token is invalid
                if (response.status === 401 || response.status === 403) {
                    throw new TokenRefreshError(`Refresh failed: ${errorDetail}`);
                }

                // For other errors, retry with exponential backoff
                throw new Error(`HTTP ${response.status}: ${errorDetail}`);
            }

            const tokenData = await response.json() as TokenData;
            console.debug(`${this.LOG_PREFIX} New tokens received, access_token: ${tokenData.access_token.substring(0, 20)}..., expires_at: ${tokenData.expires_at}`);

            // Store new tokens
            await this.storeTokens(tokenData);

            console.log(`${this.LOG_PREFIX} Token refresh successful (total time: ${Date.now() - refreshStartTime}ms)`);

            // Reset auth store refresh status on success
            auth.update(state => ({
                ...state,
                refresh_status: 'idle',
                refresh_attempt: undefined
            }));

            return tokenData;

        } catch (error) {
            const refreshDuration = Date.now() - refreshStartTime;

            if (error instanceof TokenRefreshError) {
                // Don't retry TokenRefreshError (invalid tokens)
                console.error(`${this.LOG_PREFIX} Token refresh failed permanently after ${refreshDuration}ms:`, error);
                throw error;
            }

            // Handle network/timeout errors with retry
            const isTimeout = error instanceof Error && error.name === 'AbortError';
            const isNetworkError = error instanceof TypeError && error.message.includes('fetch');
            const errorMessage = error instanceof Error ? error.message : String(error);

            console.warn(`${this.LOG_PREFIX} Refresh attempt ${attempt} failed after ${refreshDuration}ms:`,
                isTimeout ? 'Request timeout' : isNetworkError ? 'Network error' : errorMessage);

            if (attempt < maxAttempts && (isTimeout || isNetworkError || errorMessage.includes('HTTP 5'))) {
                // Exponential backoff: 1s, 2s, 4s
                const delayMs = Math.pow(2, attempt - 1) * 1000;
                console.log(`${this.LOG_PREFIX} Retrying refresh in ${delayMs}ms...`);

                await new Promise(resolve => setTimeout(resolve, delayMs));
                return this.performRefresh(attempt + 1, maxAttempts);
            }

            // Max attempts reached or non-retryable error
            console.error(`${this.LOG_PREFIX} Token refresh failed permanently after ${attempt} attempts:`, error);

            // Update auth store with failed status
            auth.update(state => ({
                ...state,
                refresh_status: 'failed',
                refresh_attempt: attempt
            }));

            throw new TokenRefreshError(`Refresh failed after ${attempt} attempts: ${errorMessage}`);
        }
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
            //console.log(`${this.LOG_PREFIX} Storing tokens in localStorage`);

            localStorage.setItem('token', tokenData.access_token);
            localStorage.setItem('token_expires', tokenData.expires_at);

            if (tokenData.refresh_token) {
                if (!tokenData.refresh_token_expires_at) {
                    throw new Error('Refresh token provided without expiry date');
                }
                localStorage.setItem('refresh_token', tokenData.refresh_token);
                localStorage.setItem('refresh_token_expires', tokenData.refresh_token_expires_at);
            }

            console.log(`${this.LOG_PREFIX} Tokens stored in localStorage.`);

            // Update auth store - tokens stored means authenticated
            auth.update(state => ({
                ...state,
                is_authenticated: true
            }));
    }

    async registerClientPublicKey(): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Registering client public key with server`);

            // Get client public key info
            const keyInfo = await clientCrypto.getPublicKeyInfo();

            // Use the HttpClient for authenticated requests

            const response = await http.post('/auth/register-client-key', {
                public_key_pem: keyInfo.public_key_pem,
                key_id: keyInfo.key_id,
                created_at: keyInfo.created_at
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(`Registration failed: ${error.detail || response.statusText}`);
            }

            console.log(`${this.LOG_PREFIX} Client public key registered successfully`);

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error registering client public key:`, error);
            throw error;
        }
    }

    async clearTokens(): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Clearing tokens from localStorage`);

            localStorage.removeItem('token');
            localStorage.removeItem('token_expires');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('refresh_token_expires');

            console.log(`${this.LOG_PREFIX} Tokens cleared successfully from localStorage`);

            // Update auth store - no tokens means not authenticated
            auth.update(state => ({
                ...state,
                is_authenticated: false,
                user: null
            }));

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error clearing tokens from localStorage:`, error);
            throw error;
        }
    }

    async isTokenExpired(bufferMinutes: number = 2): Promise<boolean> {
        try {
            const expiresAtStr = localStorage.getItem('token_expires');
            if (!expiresAtStr) {
                return true; // No expiry time means expired
            }

            const expiresAt = parsePythonDateTime(expiresAtStr);
            if (!expiresAt) {
                console.error(`${this.LOG_PREFIX} Failed to parse token expiry: ${expiresAtStr}`);
                return true; // If we can't parse, assume expired for safety
            }

            const now = new Date();
            const bufferMs = bufferMinutes * 60 * 1000;
            const isExpired = (expiresAt.getTime() - bufferMs) <= now.getTime();

            console.log(`${this.LOG_PREFIX} Token expires ${expiresAt.toISOString()}, now ${now.toISOString()}, expired: ${isExpired}`);

            if (isExpired) {
                console.log(`${this.LOG_PREFIX} Token expired or expiring soon`);
            }

            return isExpired;

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error checking token expiry:`, error);
            return true; // If we can't check, assume expired for safety
        }
    }

    /**
     * Check if refresh token is expiring soon and needs proactive renewal
     * @param bufferDays Days before expiry to trigger renewal (default: 3)
     */
    private async shouldRenewRefreshToken(bufferDays: number = 3): Promise<boolean> {
        const refreshExpiresStr = localStorage.getItem('refresh_token_expires');
        if (!refreshExpiresStr) {
            throw new Error('No refresh token expiry stored - invalid token state');
        }

        const expiresAt = parsePythonDateTime(refreshExpiresStr);
        if (!expiresAt) {
            console.error(`${this.LOG_PREFIX} Failed to parse refresh token expiry: ${refreshExpiresStr}`);
            throw new Error('Invalid refresh token expiry format');
        }

        const now = new Date();
        const bufferMs = bufferDays * 24 * 60 * 60 * 1000; // Convert days to ms

        const shouldRenew = now.getTime() + bufferMs >= expiresAt.getTime();

        if (shouldRenew) {
            const daysRemaining = Math.floor((expiresAt.getTime() - now.getTime()) / (24 * 60 * 60 * 1000));
            console.log(`${this.LOG_PREFIX} Refresh token expiring in ${daysRemaining} days, triggering proactive renewal`);
        }

        return shouldRenew;
    }
}
