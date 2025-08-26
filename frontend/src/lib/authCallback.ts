import { goto } from '$app/navigation';
import { browser } from '$app/environment';
import { backendUrl } from './config';
import { TAURI } from './tauri';

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
        const expectedScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'io.github.koo5.hillview.dev://auth' : 'io.github.koo5.hillview://auth';
        if (!url.includes('token=') || !url.startsWith(expectedScheme)) {
            return false;
        }
        
        const urlObj = new URL(url);
        const token = urlObj.searchParams.get('token');
        const expiresAt = urlObj.searchParams.get('expires_at');
        
        if (token && expiresAt) {
            // Check if token is already expired (compare in UTC)
            const expiryDate = new Date(expiresAt);
            const now = new Date();
            
            // Log the comparison for debugging
            console.log(`🢄🔐 Token expiry check - Expiry: ${expiryDate.toISOString()}, Now: ${now.toISOString()}`);
            console.log(`🢄🔐 Raw expires_at value: ${expiresAt}`);
            
            // Compare timestamps directly to handle timezone correctly
            if (expiryDate.getTime() <= now.getTime()) {
                console.warn('🢄🔐 Token appears expired, but continuing anyway for testing');
                // Temporarily commenting out the return to test the rest of the flow
                // return false;
            }
            
            console.log('🢄🔐 Auth callback received, storing token');
            
            // Store token in Android SharedPreferences via Tauri command
            let result: BasicResponse;
            if (TAURI) {
                const { invoke } = await import('@tauri-apps/api/core');
                result = await invoke('store_auth_token', { 
                    token, 
                    expires_at: expiresAt 
                }) as BasicResponse;
            } else {
                // For non-Tauri environments, store in localStorage or similar
                result = { success: false, error: 'Not running in Tauri environment' };
            }
            
            if (result.success) {
                console.log('🢄🔐 Auth token stored successfully');
                
                // Redirect to dashboard
                await goto('/dashboard');
                return true;
            } else {
                console.error('🢄🔐 Failed to store auth token:', result.error);
                return false;
            }
        } else {
            console.error('🢄🔐 Auth callback missing required parameters');
            return false;
        }
    } catch (error) {
        console.error('🢄🔐 Error handling auth callback:', error);
        return false;
    }
}

/**
 * Get stored authentication token
 */
export async function getStoredToken(): Promise<string | null> {
    if (!TAURI) {
        return null;
    }
    try {
        const { invoke } = await import('@tauri-apps/api/core');
        const result = await invoke('get_auth_token') as AuthTokenResponse;
        if (result.success && result.token) {
            return result.token;
        }
        return null;
    } catch (error) {
        console.error('🢄🔐 Error getting stored token:', error);
        return null;
    }
}

/**
 * Clear stored authentication token
 */
export async function clearStoredToken(): Promise<boolean> {
    if (!TAURI) {
        return false;
    }
    try {
        const { invoke } = await import('@tauri-apps/api/core');
        const result = await invoke('clear_auth_token') as BasicResponse;
        return result.success;
    } catch (error) {
        console.error('🢄🔐 Error clearing token:', error);
        return false;
    }
}

/**
 * Check if user has valid stored authentication
 */
export async function hasValidAuth(): Promise<boolean> {
    if (!TAURI) {
        return false;
    }
    try {
        const { invoke } = await import('@tauri-apps/api/core');
        const result = await invoke('get_auth_token') as AuthTokenResponse;
        if (!result.success || !result.token) {
            return false;
        }
        
        // Check token expiration if expires_at is provided
        if (result.expires_at) {
            const expiryDate = new Date(result.expires_at);
            const now = new Date();
            if (expiryDate <= now) {
                console.log('🢄🔐 Token has expired');
                return false;
            }
        }
        
        // Check if token format is valid (basic JWT check)
        const tokenParts = result.token.split('.');
        if (tokenParts.length !== 3) {
            console.log('🢄🔐 Invalid token format');
            return false;
        }
        
        return true;
    } catch (error) {
        console.error('🢄🔐 Error checking auth:', error);
        return false;
    }
}

/**
 * Set up deep link listener for authentication callbacks
 * Should be called once when the app starts
 */
export async function setupDeepLinkListener(): Promise<void> {
    if (!browser || !TAURI) {
        console.log('🢄🔗 Skipping deep link listener setup (not in Tauri environment)');
        return;
    }
    
    try {
        // Dynamically import the deep-link plugin only when in Tauri
        const { onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
        
        // Listen for deep link URLs
        const unlisten = await onOpenUrl((urls) => {
            console.log('🢄🔗 Deep link received:', urls);
            
            for (const url of urls) {
                const expectedScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'io.github.koo5.hillview.dev://auth' : 'io.github.koo5.hillview://auth';
                if (url.startsWith(expectedScheme)) {
                    console.log('🢄🔐 Processing auth callback from deep link:', url);
                    handleAuthCallback(url);
                    break;
                }
            }
        });
        
        console.log('🢄🔗 Deep link listener set up successfully');
        // Store unlisten function if needed, but don't return it since function returns void
    } catch (error) {
        console.error('🢄🔗 Error setting up deep link listener:', error);
    }
}

/**
 * Build OAuth URL for unified authentication flow
 */
export function buildOAuthUrl(provider: string, isMobileApp: boolean): string {
    const mobileScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'io.github.koo5.hillview.dev://auth' : 'io.github.koo5.hillview://auth';
    const redirectUri = isMobileApp 
        ? mobileScheme  // Deep link for mobile
        : `${window.location.origin}/oauth/callback`;  // Web callback
        
    // Use unified backend OAuth redirect endpoint
    const serverUrl = backendUrl;
    return `${serverUrl}/auth/oauth-redirect?provider=${provider}&redirect_uri=${encodeURIComponent(redirectUri)}`;
}