/**
 * Token Management System
 * 
 * Provides unified token management for both Android and web-only environments.
 * Handles token refresh, storage, and race condition prevention.
 */

export interface TokenData {
    access_token: string;
    refresh_token?: string;
    token_type: string;
    expires_at: string;
    refresh_token_expires_at?: string;
}

export interface TokenManager {
    /**
     * Get a valid access token, refreshing if necessary
     * @returns Valid access token or null if unable to get one
     */
    getValidToken(): Promise<string | null>;
    
    /**
     * Manually refresh the current token
     * @returns True if refresh succeeded, false otherwise
     */
    refreshToken(): Promise<boolean>;
    
    /**
     * Store new token data
     * @param tokenData Token information to store
     */
    storeTokens(tokenData: TokenData): Promise<void>;
    
    /**
     * Clear all stored tokens (logout)
     */
    clearTokens(): Promise<void>;
    
    /**
     * Check if current token is expired or expiring soon
     * @param bufferMinutes Minutes before expiry to consider expired (default: 2)
     */
    isTokenExpired(bufferMinutes?: number): Promise<boolean>;
    
    /**
     * Check if refresh token is expired or expiring soon (Web only - Android handles internally)
     * @param bufferHours Hours before expiry to consider expired (default: 1)
     */
    isRefreshTokenExpired?(bufferHours?: number): Promise<boolean>;
}

export class TokenExpiredError extends Error {
    constructor(message: string = 'Token expired and refresh failed') {
        super(message);
        this.name = 'TokenExpiredError';
    }
}

export class TokenRefreshError extends Error {
    constructor(message: string = 'Failed to refresh token') {
        super(message);
        this.name = 'TokenRefreshError';
    }
}