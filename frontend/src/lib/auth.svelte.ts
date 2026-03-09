import { get } from 'svelte/store';
import { browser } from '$app/environment';
import { http } from '$lib/http';

import { backendUrl } from './config';
import { createTokenManager } from './tokenManagerFactory';
import { auth, type User, type AuthState } from './authStore';
import { myGoto } from './navigation.svelte';
import { clearAlerts } from './alertSystem.svelte';

// Re-export for backward compatibility
export type { User, AuthState };
export { auth };


if (browser) {
	auth.subscribe(authState => {
		console.log('🢄auth store updated:', JSON.stringify(authState));
	});
}


// Shared function to complete authentication after successful login (exported for authCallback)
export async function completeAuthentication(tokenData: {
    access_token: string;
    refresh_token?: string;
    expires_at: string;
    token_type?: string;
    refresh_token_expires_at: string;
}, source: 'login' | 'oauth' = 'login'): Promise<boolean> {
        console.log(`🢄[AUTH] Completing ${source} authentication...`);

        // Store tokens using the unified TokenManager
        const tokenManager = createTokenManager();
        const tokensToStore = {
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token,
            expires_at: tokenData.expires_at,
            token_type: tokenData.token_type || 'bearer',
            refresh_token_expires_at: tokenData.refresh_token_expires_at
        };

        console.log('🢄[AUTH] About to store tokens:', JSON.stringify({
            hasAccessToken: !!tokensToStore.access_token,
            hasRefreshToken: !!tokensToStore.refresh_token,
            expiresAt: tokensToStore.expires_at,
            refreshTokenExpiresAt: tokensToStore.refresh_token_expires_at,
            tokenType: tokensToStore.token_type
        }));

        await tokenManager.storeTokens(tokensToStore);
        console.log('🢄[AUTH] Tokens stored successfully via TokenManager');

        // Clear accumulated alerts on successful login
        clearAlerts();

        // Register client public key BEFORE setting is_authenticated.
        // Like Kotlin: registration must succeed for login to succeed.
        // This prevents the race where triggerPhotoSync fires (via auth
        // subscription) before the key is registered on the server.
        if ('registerClientPublicKey' in tokenManager) {
            try {
                await (tokenManager as any).registerClientPublicKey();
                console.log('🢄[AUTH] Client public key registered');
            } catch (error: any) {
                console.error('🢄[AUTH] Key registration failed, aborting login:', error);
                await tokenManager.clearTokens();
                return false;
            }
        }

        // NOW set authenticated — key is registered, safe to trigger photo sync
        auth.update(a => ({
            ...a,
            is_authenticated: true
        }));

        // Fetch user data
		console.log('🢄[AUTH] Fetching user data after authentication...');
        const userData = await fetchUserData();
        console.log('🢄[AUTH] User data fetched:', userData);

        if (!userData) {
            console.error('🢄[AUTH] Failed to fetch user data after authentication');
            return false;
        }

        // Double-check auth state
        console.log('🢄[AUTH] Auth state after authentication:', debugAuth());

        return true;
}

// Token manager lazy initialization - will initialize on first use
let authInitialized = false;

async function ensureAuthInitialized() {
    if (authInitialized || typeof window === 'undefined') {
        return;
    }
    authInitialized = true;

    const tokenManager = createTokenManager();
    const token = await tokenManager.getValidToken();

    if (token) {
        console.log('🢄[AUTH] Valid token found during initialization');
        auth.update(state => ({
            ...state,
            is_authenticated: true
        }));
		console.log('🢄[AUTH] ensureAuthInitialized: Fetching user data during initialization...');
        fetchUserData();
    } else {
        console.log('🢄[AUTH] No valid token found during initialization');
        auth.update(a => ({ ...a, checked: true }));
    }
}

// Auth functions
export async function login(username: string, password: string) {
    await ensureAuthInitialized();
        console.log('🢄[AUTH] Logging in with:', { username });
        const response = await fetch(backendUrl+'/auth/token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            },
            body: new URLSearchParams({
                'username': username,
                'password': password,
                'grant_type': 'password'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();

        console.log('🢄[AUTH] Login successful, token received:');
        console.log('🢄[AUTH] - access_token:', data.access_token ? 'present' : 'missing');
        console.log('🢄[AUTH] - refresh_token:', data.refresh_token ? 'present' : 'missing');
        console.log('🢄[AUTH] - expires_at:', data.expires_at);
        console.log('🢄[AUTH] - refresh_token_expires_at:', data.refresh_token_expires_at);
        console.log('🢄[AUTH] - token_type:', data.token_type);

        // Use shared authentication completion
        return await completeAuthentication(data, 'login');
}

export async function register(email: string, username: string, password: string) {
        console.log('🢄[AUTH] Registering user:', { email, username });
        const response = await fetch(backendUrl+'/auth/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                email,
                username,
                password
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('🢄[AUTH] Registration error response:', errorText);
            let errorDetail;
            try {
                const errorJson = JSON.parse(errorText);
                errorDetail = errorJson.detail || 'Registration failed';
            } catch (e) {
                errorDetail = `Registration failed: ${response.status} ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }

        return true;
}

export async function oauthLogin(provider: string, code: string, redirectUri?: string) {
        const response = await fetch(backendUrl+'/auth/oauth', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider,
                code,
                redirect_uri: redirectUri
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'OAuth login failed');
        }

        const data = await response.json();

        console.log('🢄[AUTH] OAuth login successful, token received:', data);

        // Use shared authentication completion
        return await completeAuthentication(data, 'oauth');
}

export async function logout(reason?: string) {
    console.log('🢄[AUTH] === LOGGING OUT ===');
    if (reason) {
        console.log('🢄[AUTH] - Reason:', reason);
    }

    console.log('🢄[AUTH] - Clearing tokens via TokenManager');
    const tokenManager = createTokenManager();
    await tokenManager.clearTokens();
    console.log('🢄[AUTH] - Tokens cleared successfully');

    console.log('🢄[AUTH] - Updating auth store');
    auth.update(a => {
        console.log('🢄[AUTH]   - Setting is_authenticated to false');
        console.log('🢄[AUTH]   - Clearing token and user data');
        return {
            ...a,
            is_authenticated: false,
            checked: true,
            user: null
        };
    });

    console.log('🢄[AUTH] - Redirecting to login page from auth.svelte.ts');
    myGoto('/login');
    console.log('🢄[AUTH] === LOGOUT COMPLETE ===');
}

// Deprecated - use TokenManager.isTokenExpired instead
export async function isTokenExpired(): Promise<boolean> {
    const tokenManager = createTokenManager();
    return await tokenManager.isTokenExpired();
}

// Helper to get current valid token
export async function getCurrentToken(): Promise<string | null> {
    await ensureAuthInitialized();
    const tokenManager = createTokenManager();
    return await tokenManager.getValidToken();
}

export async function checkTokenValidity(): Promise<boolean> {
    const token = await getCurrentToken();

    if (!token) {
        console.log('🢄[AUTH] No valid token found');
        return false;
    }

    return true;
}

// Deprecated - use HttpClient from $lib/http instead
export async function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
    console.warn('🢄[AUTH] authenticatedFetch is deprecated. Use HttpClient from $lib/http instead');

    // Convert to relative URL if it starts with backendUrl
    const relativeUrl = url.startsWith(backendUrl) ? url.substring(backendUrl.length) : url;

    // Use the appropriate method from HttpClient
    const method = (options.method || 'GET').toUpperCase();
    switch (method) {
        case 'POST':
            return http.post(relativeUrl, options.body, options);
        case 'PUT':
            return http.put(relativeUrl, options.body, options);
        case 'DELETE':
            return http.delete(relativeUrl, options.body, options);
        default:
            return http.get(relativeUrl, options);
    }
}

export async function fetchUserData() {
    const a = get(auth);

    console.log('🢄[AUTH] fetchUserData start - Current auth state: is_authenticated:', a.is_authenticated, 'Has user:', !!a.user);

    try {
        //console.log('🢄[AUTH] Making API request to /api/auth/me');
        const response = await http.get('/auth/me');

        //console.log('🢄[AUTH] - API response status:', response.status);

        if (!response.ok) {
            console.error('🢄[AUTH] API request failed:', response.status, response.statusText);
            return null;
        }

        const userData = await response.json();
        console.log('🢄[AUTH] fetchUserData - User data received:', JSON.stringify(userData));

        // If we successfully got user data, ensure is_authenticated: is true
        auth.update(a => {
            return {
                ...a,
                is_authenticated: true,
                checked: true,
                user: userData
            };
        });
        console.log('🢄[AUTH] === USER DATA FETCH COMPLETE ===');
        return userData;
    } catch (error) {
        console.error('🢄[AUTH] Error fetching user data:', error);
        // If it's a TokenExpiredError, logout was already handled by the http client
        // For other errors, mark as checked so auth-gated pages stop waiting
        auth.update(a => ({ ...a, checked: true }));
        return null;
    }
}

// Check token validity on app start
export async function checkAuth() {
    const a = get(auth);

    console.log('🢄[AUTH] - is_authenticated:', a.is_authenticated, 'a.user:', JSON.stringify(a.user));

    // Check token validity through TokenManager
    const validToken = await getCurrentToken();
    //console.log('🢄[AUTH] - Has valid token:', !!validToken);
    if (validToken) {
        console.log('🢄[AUTH]3 - Token preview:', validToken.substring(0, 10) + '...');
    }

    // If we have a valid token, fetch user data
    if (validToken) {
        console.log('🢄[AUTH] checkAuth: Valid token found, fetching user data');
        fetchUserData();
    } else if (a.user) {
        // We have user data but no valid token - inconsistent state
        console.warn('🢄[AUTH] INCONSISTENT STATE: User data exists but no valid token');
        console.warn('🢄[AUTH] Logging out due to invalid token');
        logout('Invalid token');
    } else if (a.is_authenticated && !a.user) {
        // We think we're authenticated but have no user data - fetch it
        console.warn('🢄[AUTH] INCONSISTENT STATE: Authenticated but no user data');
        console.warn('🢄[AUTH] Attempting to fetch user data');
        fetchUserData();
    } else {
        // Not authenticated
        console.log('🢄[AUTH] Not authenticated');
        auth.update(a => ({ ...a, checked: true }));
    }
}

// Debug function to log auth state
export function debugAuth() {
    const a = get(auth);
    console.log('🢄[AUTH] Auth state:', {
        is_authenticated: a.is_authenticated,
        hasUser: !!a.user,
        user: a.user
    });
    return a;
}
