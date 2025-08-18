import { invoke } from '@tauri-apps/api/core';
import { goto } from '$app/navigation';
import { browser } from '$app/environment';
import { onOpenUrl } from '@tauri-apps/plugin-deep-link';
import { backendUrl } from './config';

export interface AuthToken {
    token: string;
    expires_at: string;
}

export interface AuthTokenResponse {
    token?: string;
    expires_at?: string;
    success: boolean;
    error?: string;
}

export interface BasicResponse {
    success: boolean;
    error?: string;
}

/**
 * Handle authentication callback from deep link
 * This function should be called when the app receives a deep link like:
 * com.hillview://auth?token=JWT_HERE&expires_at=2023-...
 */
export async function handleAuthCallback(url?: string): Promise<boolean> {
    if (!browser) return false;
    
    try {
        // If no URL provided, try to get it from current location
        if (!url) {
            url = window.location.href;
        }
        
        // Check if this is an auth callback URL
        if (!url.includes('token=') || !url.startsWith('com.hillview://auth')) {
            return false;
        }
        
        const urlObj = new URL(url);
        const token = urlObj.searchParams.get('token');
        const expiresAt = urlObj.searchParams.get('expires_at');
        
        if (token && expiresAt) {
            // Check if token is already expired
            const expiryDate = new Date(expiresAt);
            const now = new Date();
            if (expiryDate <= now) {
                console.error('🔐 Auth callback token is already expired');
                return false;
            }
            
            console.log('🔐 Auth callback received, storing token');
            
            // Store token in Android SharedPreferences via Tauri command
            const result = await invoke('store_auth_token', { 
                token, 
                expiresAt 
            }) as BasicResponse;
            
            if (result.success) {
                console.log('🔐 Auth token stored successfully');
                
                // Redirect to dashboard
                await goto('/dashboard');
                return true;
            } else {
                console.error('🔐 Failed to store auth token:', result.error);
                return false;
            }
        } else {
            console.error('🔐 Auth callback missing required parameters');
            return false;
        }
    } catch (error) {
        console.error('🔐 Error handling auth callback:', error);
        return false;
    }
}

/**
 * Get stored authentication token
 */
export async function getStoredToken(): Promise<string | null> {
    try {
        const result = await invoke('get_auth_token') as AuthTokenResponse;
        if (result.success && result.token) {
            return result.token;
        }
        return null;
    } catch (error) {
        console.error('🔐 Error getting stored token:', error);
        return null;
    }
}

/**
 * Clear stored authentication token
 */
export async function clearStoredToken(): Promise<boolean> {
    try {
        const result = await invoke('clear_auth_token') as BasicResponse;
        return result.success;
    } catch (error) {
        console.error('🔐 Error clearing token:', error);
        return false;
    }
}

/**
 * Check if user has valid stored authentication
 */
export async function hasValidAuth(): Promise<boolean> {
    try {
        const result = await invoke('get_auth_token') as AuthTokenResponse;
        if (!result.success || !result.token) {
            return false;
        }
        
        // Check token expiration if expires_at is provided
        if (result.expires_at) {
            const expiryDate = new Date(result.expires_at);
            const now = new Date();
            if (expiryDate <= now) {
                console.log('🔐 Token has expired');
                return false;
            }
        }
        
        // Check if token format is valid (basic JWT check)
        const tokenParts = result.token.split('.');
        if (tokenParts.length !== 3) {
            console.log('🔐 Invalid token format');
            return false;
        }
        
        return true;
    } catch (error) {
        console.error('🔐 Error checking auth:', error);
        return false;
    }
}

/**
 * Set up deep link listener for authentication callbacks
 * Should be called once when the app starts
 */
export async function setupDeepLinkListener(): Promise<void> {
    if (!browser) return;
    
    try {
        // Listen for deep link URLs
        const unlisten = await onOpenUrl((urls) => {
            console.log('🔗 Deep link received:', urls);
            
            for (const url of urls) {
                if (url.startsWith('com.hillview://auth')) {
                    console.log('🔐 Processing auth callback from deep link:', url);
                    handleAuthCallback(url);
                    break;
                }
            }
        });
        
        console.log('🔗 Deep link listener set up successfully');
        return unlisten;
    } catch (error) {
        console.error('🔗 Error setting up deep link listener:', error);
    }
}

/**
 * Build OAuth URL for unified authentication flow
 */
export function buildOAuthUrl(provider: string, isMobileApp: boolean): string {
    const redirectUri = isMobileApp 
        ? "com.hillview://auth"  // Deep link for mobile
        : `${window.location.origin}/oauth/callback`;  // Web callback
        
    // Use unified backend OAuth redirect endpoint
    const serverUrl = backendUrl;
    return `${serverUrl}/auth/oauth-redirect?provider=${provider}&redirect_uri=${encodeURIComponent(redirectUri)}`;
}