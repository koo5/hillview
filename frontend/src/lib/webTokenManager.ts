import type { TokenManager, TokenData } from './tokenManager';
import { TokenExpiredError, TokenRefreshError } from './tokenManager';
import { backendUrl } from './config';
import { auth } from './authStore';
import { clientCrypto } from './clientCrypto';
import { http } from '$lib/http';

/**
 * Web Token Manager
 * 
 * Handles token management for web-only environments using localStorage.
 * Implements race condition protection through promise deduplication.
 */
export class WebTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🔐[WEB_TOKEN_MGR]';
    private refreshPromise: Promise<TokenData> | null = null;

    async getValidToken(): Promise<string | null> {
        try {
            console.log(`${this.LOG_PREFIX} Getting valid token from localStorage`);
            
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
                console.log(`${this.LOG_PREFIX} No token in localStorage`);
                return null;
            }
            
            // Check if token is expired
            if (await this.isTokenExpired()) {
                console.log(`${this.LOG_PREFIX} Token expired, attempting refresh`);
                
                // Start refresh process
                this.refreshPromise = this.performRefresh();
                
                try {
                    const newToken = await this.refreshPromise;
                    this.refreshPromise = null;
                    return newToken.access_token;
                } catch (error) {
                    this.refreshPromise = null;
                    console.error(`${this.LOG_PREFIX} Refresh failed:`, error);
                    // Refresh failed means authentication is lost
                    auth.update(state => ({
                        ...state,
                        isAuthenticated: false,
                        user: null
                    }));
                    throw new TokenExpiredError('Token expired and refresh failed');
                }
            }
            
            console.log(`${this.LOG_PREFIX} Returning valid token from localStorage`);
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

    private async performRefresh(): Promise<TokenData> {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            throw new TokenRefreshError('No refresh token available');
        }
        
        console.log(`${this.LOG_PREFIX} Performing token refresh...`);
        
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
            const error = await response.json();
            throw new TokenRefreshError(`Refresh failed: ${error.detail || response.statusText}`);
        }
        
        const tokenData = await response.json() as TokenData;
        
        // Store new tokens
        await this.storeTokens(tokenData);
        
        console.log(`${this.LOG_PREFIX} Token refresh successful`);
        return tokenData;
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Storing tokens in localStorage`);
            
            localStorage.setItem('token', tokenData.access_token);
            localStorage.setItem('token_expires', tokenData.expires_at);
            
            if (tokenData.refresh_token) {
                localStorage.setItem('refresh_token', tokenData.refresh_token);
            }
            
            console.log(`${this.LOG_PREFIX} Tokens stored successfully in localStorage`);
            
            // Update auth store - tokens stored means authenticated
            auth.update(state => ({
                ...state,
                isAuthenticated: true
            }));
            
            // Register client public key with server after successful authentication
            try {
                await this.registerClientPublicKey();
            } catch (error) {
                console.error(`${this.LOG_PREFIX} Failed to register client public key:`, error);
                // Don't fail the login process, but log the error
            }
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error storing tokens in localStorage:`, error);
            throw error;
        }
    }

    private async registerClientPublicKey(): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Registering client public key with server`);
            
            // Get client public key info
            const keyInfo = await clientCrypto.getPublicKeyInfo();
            
            // Use the HttpClient for authenticated requests
            
            const response = await http.post('/auth/register-client-key', {
                public_key_pem: keyInfo.publicKeyPem,
                key_id: keyInfo.keyId,
                created_at: keyInfo.createdAt
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
            
            console.log(`${this.LOG_PREFIX} Tokens cleared successfully from localStorage`);
            
            // Update auth store - no tokens means not authenticated
            auth.update(state => ({
                ...state,
                isAuthenticated: false,
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
            
            const expiresAt = new Date(expiresAtStr + 'Z'); // Add Z for UTC
            const now = new Date();
            const bufferMs = bufferMinutes * 60 * 1000;
            
            const isExpired = (expiresAt.getTime() - bufferMs) <= now.getTime();
            
            if (isExpired) {
                console.log(`${this.LOG_PREFIX} Token expired or expiring soon`);
            }
            
            return isExpired;
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error checking token expiry:`, error);
            return true; // If we can't check, assume expired for safety
        }
    }
}