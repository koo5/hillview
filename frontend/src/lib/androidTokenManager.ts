import { invoke } from '@tauri-apps/api/core';
import type { TokenManager, TokenData } from './tokenManager';
import { TokenExpiredError, TokenRefreshError } from './tokenManager';

/**
 * Android Token Manager
 * 
 * Delegates all token operations to the Android plugin, which handles
 * refresh logic with mutex protection to prevent race conditions.
 */
export class AndroidTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🔐[ANDROID_TOKEN_MGR]';

    async getValidToken(): Promise<string | null> {
        try {
            console.log(`${this.LOG_PREFIX} Getting valid token from Android`);
            
            // Android plugin handles token validation and refresh internally
            const result = await invoke('plugin:hillview|get_auth_token') as { 
                token: string | null; 
                expires_at: string | null;
                success: boolean;
                error?: string;
            };
            
            if (!result.success) {
                console.log(`${this.LOG_PREFIX} Android reports no valid token: ${result.error}`);
                return null;
            }
            
            if (result.token) {
                console.log(`${this.LOG_PREFIX} Valid token received from Android`);
                return result.token;
            }
            
            console.log(`${this.LOG_PREFIX} No token available`);
            return null;
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error getting token from Android:`, error);
            return null;
        }
    }

    async refreshToken(): Promise<boolean> {
        try {
            console.log(`${this.LOG_PREFIX} Requesting token refresh from Android`);
            
            const result = await invoke('plugin:hillview|refresh_auth_token') as {
                success: boolean;
                error?: string;
            };
            
            if (result.success) {
                console.log(`${this.LOG_PREFIX} Token refresh successful`);
                return true;
            } else {
                console.log(`${this.LOG_PREFIX} Token refresh failed: ${result.error}`);
                return false;
            }
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error refreshing token:`, error);
            throw new TokenRefreshError(`Android token refresh failed: ${error}`);
        }
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Storing tokens in Android`);
            
            await invoke('plugin:hillview|store_auth_token', {
                token: tokenData.access_token,
                refreshToken: tokenData.refresh_token,
                expiresAt: tokenData.expires_at
            });
            
            console.log(`${this.LOG_PREFIX} Tokens stored successfully in Android`);
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error storing tokens in Android:`, error);
            throw error;
        }
    }

    async clearTokens(): Promise<void> {
        try {
            console.log(`${this.LOG_PREFIX} Clearing tokens in Android`);
            
            await invoke('plugin:hillview|clear_auth_token');
            
            console.log(`${this.LOG_PREFIX} Tokens cleared successfully from Android`);
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error clearing tokens from Android:`, error);
            throw error;
        }
    }

    async isTokenExpired(bufferMinutes: number = 2): Promise<boolean> {
        try {
            const result = await invoke('plugin:hillview|is_token_expired', {
                bufferMinutes
            }) as { expired: boolean };
            
            return result.expired;
            
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error checking token expiry:`, error);
            // If we can't check, assume it's expired for safety
            return true;
        }
    }
}