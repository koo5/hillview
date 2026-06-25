import { get } from 'svelte/store';
import { browser } from '$app/environment';
import { http } from '$lib/http';

import { backendUrl } from './config';
import { createTokenManager } from './tokenManagerFactory';
import { auth, type User, type AuthState } from './authStore';
import { myGoto } from './navigation.svelte';
import { clearAlerts } from './alertSystem.svelte';
import { identify } from './analytics';
import { simplePhotoWorker } from './simplePhotoWorker';
import { onReconnect } from './connectivity';

const doLog = false;

// Re-export for backward compatibility
export type { User, AuthState };
export { auth };


if (browser) {
	auth.subscribe(authState => {
		if (doLog) console.log('🢄auth store updated:', JSON.stringify(authState));
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
        if (doLog) console.log(`🢄[AUTH] Completing ${source} authentication...`);

        // Store tokens using the unified TokenManager
        const tokenManager = createTokenManager();
        const tokensToStore = {
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token,
            expires_at: tokenData.expires_at,
            token_type: tokenData.token_type || 'bearer',
            refresh_token_expires_at: tokenData.refresh_token_expires_at
        };

        if (doLog) console.log('🢄[AUTH] About to store tokens:', JSON.stringify({
            hasAccessToken: !!tokensToStore.access_token,
            hasRefreshToken: !!tokensToStore.refresh_token,
            expiresAt: tokensToStore.expires_at,
            refreshTokenExpiresAt: tokensToStore.refresh_token_expires_at,
            tokenType: tokensToStore.token_type
        }));

        await tokenManager.storeTokens(tokensToStore);
        if (doLog) console.log('🢄[AUTH] Tokens stored successfully via TokenManager');

        // Clear accumulated alerts on successful login
        clearAlerts();

        // Register client public key BEFORE setting is_authenticated.
        // Like Kotlin: registration must succeed for login to succeed.
        // This prevents the race where triggerPhotoSync fires (via auth
        // subscription) before the key is registered on the server.
        if ('registerClientPublicKey' in tokenManager) {
            try {
                await (tokenManager as any).registerClientPublicKey();
                if (doLog) console.log('🢄[AUTH] Client public key registered');
            } catch (error: any) {
                console.error('🢄[AUTH] Key registration failed, aborting login:', error);
                await tokenManager.clearTokens();
                return false;
            }
        }

        // NOW set authenticated — key is registered, safe to trigger photo sync.
        // Bump the auth generation first so any logout() requested by a stale /
        // in-flight request from the previous session is ignored and cannot clear
        // this freshly established session.
        bumpAuthGeneration();
        auth.update(a => ({
            ...a,
            is_authenticated: true
        }));

        // Fetch user data
		if (doLog) console.log('🢄[AUTH] Fetching user data after authentication...');
        const userData = await fetchUserData();
        if (doLog) console.log('🢄[AUTH] User data fetched:', userData);

        if (!userData) {
            console.error('🢄[AUTH] Failed to fetch user data after authentication');
            return false;
        }

        // Double-check auth state
        if (doLog) console.log('🢄[AUTH] Auth state after authentication:', debugAuth());

        return true;
}

// Auth session generation. Incremented on every successful (re)authentication.
// Lets logout() ignore calls triggered by requests that began in an earlier
// session, so a late / in-flight 401 from before a re-login can't tear down the
// fresh session (see completeAuthentication and logout below).
let authGeneration = 0;
export function getAuthGeneration(): number {
    return authGeneration;
}
// Bump when a new session is established (login here, or a login synced from
// another tab). Stale requests captured an older generation and are then ignored
// by logout().
export function bumpAuthGeneration(): number {
    return ++authGeneration;
}

// Token manager lazy initialization - will initialize on first use
let authInitialized = false;

async function ensureAuthInitialized() {
    if (authInitialized || typeof window === 'undefined') {
        return;
    }
    authInitialized = true;

    const tokenManager = createTokenManager();
    // A terminal failure throws here (getValidToken has already logged out); a
    // transient failure returns null with the session intact. Either way there's
    // no token to use right now, and we must not let a terminal throw escape as an
    // uncaught error during startup.
    let token: string | null = null;
    try {
        token = await tokenManager.getValidToken();
    } catch (error) {
        if (doLog) console.log('🢄[AUTH] Token check failed during initialization (already handled):', error);
    }

    if (token) {
        if (doLog) console.log('🢄[AUTH] Valid token found during initialization');
        auth.update(state => ({
            ...state,
            is_authenticated: true
        }));
		if (doLog) console.log('🢄[AUTH] ensureAuthInitialized: Fetching user data during initialization...');
        fetchUserData();
    } else {
        if (doLog) console.log('🢄[AUTH] No valid token found during initialization');
        auth.update(a => ({ ...a, checked: true }));
    }
}

// Auth functions
export async function login(username: string, password: string) {
    // Don't call ensureAuthInitialized() here — login replaces any existing auth state.
    // Calling it with a stale token would fire-and-forget fetchUserData(), whose
    // eventual 401 → logout() races with and clears the fresh token from completeAuthentication().
        if (doLog) console.log('🢄[AUTH] Logging in with:', { username });
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

        if (doLog) console.log('🢄[AUTH] Login successful, token received:');
        if (doLog) console.log('🢄[AUTH] - access_token:', data.access_token ? 'present' : 'missing');
        if (doLog) console.log('🢄[AUTH] - refresh_token:', data.refresh_token ? 'present' : 'missing');
        if (doLog) console.log('🢄[AUTH] - expires_at:', data.expires_at);
        if (doLog) console.log('🢄[AUTH] - refresh_token_expires_at:', data.refresh_token_expires_at);
        if (doLog) console.log('🢄[AUTH] - token_type:', data.token_type);

        // Use shared authentication completion
        return await completeAuthentication(data, 'login');
}

export async function register(email: string, username: string, password: string) {
        if (doLog) console.log('🢄[AUTH] Registering user:', { email, username });
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

        if (doLog) console.log('🢄[AUTH] OAuth login successful, token received:', data);

        // Use shared authentication completion
        return await completeAuthentication(data, 'oauth');
}

export async function logout(reason?: string, opts?: { generation?: number }) {
    // Ignore a logout requested by a stale caller: if it was triggered by a request
    // that started in an earlier auth generation than the current one, a newer login
    // has since replaced the session and must not be torn down by the late failure.
    if (opts?.generation !== undefined && opts.generation !== authGeneration) {
        console.log(`🢄[AUTH] Ignoring stale logout (request gen ${opts.generation}, current gen ${authGeneration})${reason ? ` — reason was: ${reason}` : ''}`);
        return;
    }

    console.log('🢄[AUTH] === LOGGING OUT ===');
    if (reason) {
        console.log('🢄[AUTH] - Reason:', reason);
    }

    if (doLog) console.log('🢄[AUTH] - Clearing tokens via TokenManager');
    const tokenManager = createTokenManager();
    await tokenManager.clearTokens();
    if (doLog) console.log('🢄[AUTH] - Tokens cleared successfully');

    if (doLog) console.log('🢄[AUTH] - Updating auth store');
    auth.update(a => {
        if (doLog) console.log('🢄[AUTH]   - Setting is_authenticated to false');
        if (doLog) console.log('🢄[AUTH]   - Clearing token and user data');
        return {
            ...a,
            is_authenticated: false,
            checked: true,
            user: null,
            userStatus: 'idle'
        };
    });

    // Drop the worker's authenticated Panoramax hidden-content cache; next pan
    // will fetch with no token (→ empty hide set) until the user logs in again.
    simplePhotoWorker.invalidatePanoramaxHidden?.();

    if (doLog) console.log('🢄[AUTH] - Redirecting to login page from auth.svelte.ts');
    myGoto('/login');
    if (doLog) console.log('🢄[AUTH] === LOGOUT COMPLETE ===');
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
        if (doLog) console.log('🢄[AUTH] No valid token found');
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

// The user profile comes from a separate /auth/me request, so it's just data with
// its own load lifecycle — independent of is_authenticated. fetchUserData is the one
// place that fetches it; it dedupes concurrent calls and maintains auth.userStatus so
// views can show a spinner / retry instead of mistaking a missing profile for logout.
let userFetchPromise: Promise<User | null> | null = null;

export function fetchUserData(): Promise<User | null> {
    if (userFetchPromise) {
        if (doLog) console.log('🢄[AUTH] fetchUserData already in flight; reusing');
        return userFetchPromise;
    }
    const p = performUserFetch();
    userFetchPromise = p;
    void p.finally(() => {
        if (userFetchPromise === p) userFetchPromise = null;
    });
    return p;
}

async function performUserFetch(): Promise<User | null> {
    const a = get(auth);

    if (doLog) console.log('🢄[AUTH] fetchUserData start - Current auth state: is_authenticated:', a.is_authenticated, 'Has user:', !!a.user);

    // Only flip to 'loading' (which makes views show a spinner) when there's no
    // profile yet; a background refresh of an already-loaded profile keeps 'loaded'.
    auth.update(s => ({ ...s, userStatus: s.user ? s.userStatus : 'loading' }));

    try {
        const response = await http.get('/auth/me');

        if (!response.ok) {
            console.error('🢄[AUTH] API request failed:', response.status, response.statusText);
            auth.update(s => ({ ...s, checked: true, userStatus: s.user ? s.userStatus : 'error' }));
            return null;
        }

        const userData = await response.json();
        if (doLog) console.log('🢄[AUTH] fetchUserData - User data received:', JSON.stringify(userData));

        // If we successfully got user data, ensure is_authenticated: is true
        auth.update(a => {
            return {
                ...a,
                is_authenticated: true,
                checked: true,
                user: userData,
                userStatus: 'loaded'
            };
        });
        identify(userData.id, {name: userData.username});
        if (doLog) console.log('🢄[AUTH] === USER DATA FETCH COMPLETE ===');
        return userData;
    } catch (error) {
        if (error instanceof Error && error.name === 'TokenExpiredError') {
            // Terminal: the HTTP client already cleared tokens and logged out, which
            // resets userStatus to 'idle' — don't override that here.
            console.warn('🢄[AUTH] Session expired during user data fetch');
            auth.update(a => ({ ...a, checked: true }));
        } else {
            // Transient/other failure: keep the session, mark the profile load failed
            // (unless we still have a previously-loaded profile to show).
            console.error('🢄[AUTH] Error fetching user data:', error);
            auth.update(s => ({ ...s, checked: true, userStatus: s.user ? s.userStatus : 'error' }));
        }
        return null;
    }
}

/**
 * Fetch the profile if we're authenticated but don't have it yet — but NOT after a
 * failed load ('error'), to avoid a tight retry loop. This is the auto-loader wired to
 * auth-state changes; recovery from 'error' goes through retryUserData (reconnect /
 * manual retry button).
 */
export function ensureUserLoaded(): void {
    const a = get(auth);
    if (a.is_authenticated && !a.user && a.userStatus !== 'loading' && a.userStatus !== 'error') {
        fetchUserData();
    }
}

/**
 * Force a profile refetch when authenticated but missing it — including from the
 * 'error' state. For reconnect handlers and a manual "retry" affordance.
 */
export function retryUserData(): void {
    const a = get(auth);
    if (a.is_authenticated && !a.user) {
        if (doLog) console.log('🢄[AUTH] Retrying user data fetch');
        fetchUserData();
    }
}

// Wire the triggers once, in the browser only.
if (browser) {
    // Auto-load: whenever auth state changes to "authenticated but profile missing"
    // (e.g. after login, a token refresh, or a cross-tab login), pull the profile.
    auth.subscribe(() => ensureUserLoaded());

    // Recovery: a transient /auth/me failure leaves userStatus 'error'; retry it when
    // connectivity returns or the tab is refocused, so the UI heals without a reload.
    onReconnect(retryUserData);
}

// Check token validity on app start
export async function checkAuth() {
    const a = get(auth);

    if (doLog) console.log('🢄[AUTH] - is_authenticated:', a.is_authenticated, 'a.user:', JSON.stringify(a.user));

    // Check token validity through TokenManager.
    // A thrown error means a terminal failure — getValidToken has already logged
    // out, so there's nothing more to do. A null return means no usable token,
    // which (since a terminal failure would have thrown) is either "not logged in"
    // or a transient connectivity failure — in neither case do we log out and
    // discard the session over a blip.
    let validToken: string | null = null;
    try {
        validToken = await getCurrentToken();
    } catch (error) {
        if (doLog) console.log('🢄[AUTH] checkAuth: token check failed terminally (already logged out):', error);
        return;
    }

    if (validToken) {
        if (doLog) console.log('🢄[AUTH]3 - Token preview:', validToken.substring(0, 10) + '...');
        if (doLog) console.log('🢄[AUTH] checkAuth: Valid token found, fetching user data');
        fetchUserData();
    } else if (a.is_authenticated || a.user) {
        // No usable token but we still consider ourselves logged in. A terminal
        // failure would have thrown above and logged out, so this is a transient
        // connectivity failure — keep the session and let a later request/reconnect
        // refresh it. Do NOT log out and bounce to /login over a blip.
        console.warn('🢄[AUTH] checkAuth: no usable token (transient); keeping session, will retry');
        if (!a.user) fetchUserData();
    } else {
        // Not authenticated
        if (doLog) console.log('🢄[AUTH] Not authenticated');
        auth.update(a => ({ ...a, checked: true }));
    }
}

// Debug function to log auth state
export function debugAuth() {
    const a = get(auth);
    if (doLog) console.log('🢄[AUTH] Auth state:', {
        is_authenticated: a.is_authenticated,
        hasUser: !!a.user,
        user: a.user
    });
    return a;
}
