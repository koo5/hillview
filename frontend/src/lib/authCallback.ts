import { browser } from '$app/environment';
import { backendUrl } from './config';
import { TAURI } from './tauri';
import { completeAuthentication } from './auth.svelte';
import { myGoto } from './navigation.svelte';
import { invoke } from '@tauri-apps/api/core';
import { onOpenUrl } from '@tauri-apps/plugin-deep-link';
import { addAlert } from './alertSystem.svelte';

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
 * cz.hillview://auth?token=JWT_HERE&expires_at=2023-...
 */
export async function handleAuthCallback(url?: string): Promise<boolean> {
    if (!browser) return false;

    try {
        // If no URL provided, try to get it from current location
        if (!url) {
            url = window.location.href;
        }

        // Check if this is an auth callback URL
        const expectedScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'cz.hillviedev://auth' : 'cz.hillview://auth';
        if (!url.includes('token=') || !url.startsWith(expectedScheme)) {
            return false;
        }

        const urlObj = new URL(url);
        const token = urlObj.searchParams.get('token');
        const refreshToken = urlObj.searchParams.get('refresh_token');
        const expiresAt = urlObj.searchParams.get('expires_at');
        const refreshTokenExpiresAt = urlObj.searchParams.get('refresh_token_expires_at');

        if (token && expiresAt && refreshTokenExpiresAt) {
            // Check if token is already expired (compare in UTC)
            const expiryDate = new Date(expiresAt);
            const now = new Date();

            // Log the comparison for debugging
            console.log(`🢄🔐 Token expiry check - Expiry: ${expiryDate.toISOString()}, Now: ${now.toISOString()}`);
            console.log(`🢄🔐 Raw expires_at value: ${expiresAt}`);

            // Compare timestamps directly to handle timezone correctly
            if (expiryDate.getTime() <= now.getTime()) {
                console.warn('🢄🔐 Token is expired, rejecting authentication');
                addAlert('Login failed: authentication token has expired. Please try again.', 'error', {
                    source: 'auth_callback',
                    duration: 0,
                });
                return false;
            }

            console.log('🢄🔐 Auth callback received, completing authentication');

            // Use shared authentication completion function
            const success = await completeAuthentication({
                access_token: token,
                refresh_token: refreshToken || undefined,
                expires_at: expiresAt,
                token_type: 'bearer',
                refresh_token_expires_at: refreshTokenExpiresAt
            }, 'oauth');

            if (success) {
                console.log('🢄🔐 OAuth authentication completed successfully');
                // Redirect to dashboard
                await myGoto('/');
                return true;
            } else {
                console.error('🢄🔐 OAuth authentication completion failed');
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
        const result = await invoke('plugin:hillview|get_auth_token') as AuthTokenResponse;
        if (result.success && result.token) {
            return result.token;
        }
        return null;
    } catch (err) {
        console.error('🢄🔐 Failed to get stored token:', err);
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
        const result = await invoke('plugin:hillview|clear_auth_token') as BasicResponse;
        return result.success;
    } catch (err) {
        console.error('🢄🔐 Failed to clear stored token:', err);
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
        const result = await invoke('plugin:hillview|get_auth_token') as AuthTokenResponse;
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
    } catch (err) {
        console.error('🢄🔐 Failed to check auth validity:', err);
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

    // Listen for deep link URLs
    const unlisten = await onOpenUrl(async (urls) => {
            console.log('🢄🔗 Deep link received:', urls);

            for (const url of urls) {
                const expectedScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'cz.hillviedev://auth' : 'cz.hillview://auth';
                if (url.startsWith(expectedScheme)) {
                    console.log('🢄🔐 Processing auth callback from deep link:', url);
                    const success = await handleAuthCallback(url);
                    if (!success) {
                        console.error('🢄🔐 Auth callback failed for deep link:', url);
                    }
                    break;
                }
            }
        });

        //console.log('🢄🔗 Deep link listener set up successfully');
        // Store unlisten function if needed, but don't return it since function returns void
}

/**
 * Build OAuth URL for unified authentication flow
 */
export function buildOAuthUrl(provider: string, isMobileApp: boolean): string {
    const mobileScheme = import.meta.env.VITE_DEV_MODE === 'true' ? 'cz.hillviedev://auth' : 'cz.hillview://auth';
    const redirectUri = isMobileApp
        ? mobileScheme  // Deep link for mobile
        : `${window.location.origin}/oauth/callback`;  // Web callback

    // Use unified backend OAuth redirect endpoint
    const serverUrl = backendUrl;
    return `${serverUrl}/auth/oauth-redirect?provider=${provider}&redirect_uri=${encodeURIComponent(redirectUri)}`;
}
