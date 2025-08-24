import { writable, type Writable, get } from 'svelte/store';
import { goto } from "$app/navigation";
import { userPhotos } from './stores';
import { backendUrl } from './config';

export interface User {
    id: string;
    username: string;
    email: string;
    auto_upload_enabled?: boolean;
    auto_upload_folder?: string;
    [key: string]: unknown;
}

export interface AuthState {
    isAuthenticated: boolean;
    token: string | null;
    tokenExpires: Date | null;
    user: User | null;
}

// Check for existing token
const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
const tokenExpires = typeof localStorage !== 'undefined' ? localStorage.getItem('token_expires') : null;
const isAuthenticated = !!(token && tokenExpires && new Date(tokenExpires + 'Z') > new Date());

console.log('🢄[AUTH]  Auth initialization:');
console.log('🢄[AUTH]  - Token exists:', !!token);
console.log('🢄[AUTH]  - Token expires:', tokenExpires);
console.log('🢄[AUTH]  - Is authenticated:', isAuthenticated);
if (token) {
    console.log('🢄[AUTH]1  - Token preview:', token.substring(0, 10) + '...');
}

// Auth store
export const auth: Writable<AuthState> = writable({
    isAuthenticated,
    token,
    tokenExpires: tokenExpires ? new Date(tokenExpires + 'Z') : null,
    user: null
});

// If we have a token but isAuthenticated is false, this might be a bug
// Let's check the token validity immediately
if (token && !isAuthenticated && tokenExpires) {
    console.log('🢄[AUTH]  Token exists but isAuthenticated is false, checking token validity');
    const expiry = new Date(tokenExpires + 'Z');
    const now = new Date();
    console.log('🢄[AUTH]  - Token expiry:', expiry);
    console.log('🢄[AUTH]  - Current time:', now);
    console.log('🢄[AUTH]  - Time difference (ms):', expiry.getTime() - now.getTime());
    
    if (expiry > now) {
        console.log('🢄[AUTH]  Token is still valid, setting isAuthenticated to true');
        auth.update(state => ({
            ...state,
            isAuthenticated: true
        }));
    } else {
        console.log('🢄[AUTH]  Token has expired, not setting isAuthenticated');
    }
}

// Auth functions
export async function login(username: string, password: string) {
    try {
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
        
        console.log('🢄[AUTH] auth Login successful, token received:', data);
        
        // Store token
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('token_expires', data.expires_at);
        
        // Store token in Android SharedPreferences via Tauri command
        if (TAURI) {
            try {
                const { invoke } = await import('@tauri-apps/api/core');
                await invoke('store_auth_token', { 
                    token: data.access_token, 
                    expiresAt: data.expires_at 
                });
                console.log('🢄[AUTH] Auth token stored in Android SharedPreferences');
            } catch (error) {
                console.error('🢄[AUTH] Failed to store auth token in Android:', error);
            }
        }
        
        // Update auth store with token info first
        auth.update(a => {
            console.log('🢄[AUTH] auth Setting token and isAuthenticated to true');
            return {
                ...a,
                isAuthenticated: true,
                token: data.access_token,
                tokenExpires: new Date(data.expires_at + 'Z')
            };
        });
        
        // Fetch user data
        const userData = await fetchUserData();
        console.log('🢄[AUTH] User data fetched:', userData);
        
        // Ensure isAuthenticated is still true after fetching user data
        auth.update(a => {
            if (!a.isAuthenticated && a.user) {
                console.log('🢄[AUTH] Fixing inconsistent state: user exists but not authenticated');
                return {
                    ...a,
                    isAuthenticated: true
                };
            }
            return a;
        });
        
        // Double-check auth state
        console.log('🢄[AUTH] Auth state after login:', debugAuth());
        
        return true;
    } catch (error) {
        console.error('🢄[AUTH] Login error:', error);
        return false;
    }
}

export async function register(email: string, username: string, password: string) {
    try {
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
    } catch (error) {
        console.error('🢄[AUTH] Registration error:', error);
        return false;
    }
}

export async function oauthLogin(provider: string, code: string, redirectUri?: string) {
    try {
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
        
        // Store token
        console.log('🢄[AUTH]o OAuth login successful, token received:', data);
        console.log('🢄[AUTH]o - Storing token in localStorage');
        console.log('🢄[AUTH]o - Token preview:', data.access_token.substring(0, 10) + '...');
        console.log('🢄[AUTH]o - Token expires at:', data.expires_at);

        localStorage.setItem('token', data.access_token);
        localStorage.setItem('token_expires', data.expires_at);
        
        // Update auth store
        auth.update(a => ({
            ...a,
            isAuthenticated: true,
            token: data.access_token,
            tokenExpires: new Date(data.expires_at + 'Z')
        }));
        
        // Fetch user data
        await fetchUserData();
        
        return true;
    } catch (error) {
        console.error('🢄[AUTH]o OAuth login error:', error);
        return false;
    }
}

export function logout(reason?: string) {
    console.log('🢄[AUTH] === LOGGING OUT ===');
    if (reason) {
        console.log('🢄[AUTH] - Reason:', reason);
    }
    console.log('🢄[AUTH] - Removing token from localStorage');
    localStorage.removeItem('token');
    localStorage.removeItem('token_expires');
    
    console.log('🢄[AUTH] - Updating auth store');
    auth.update(a => {
        console.log('🢄[AUTH]   - Setting isAuthenticated to false');
        console.log('🢄[AUTH]   - Clearing token and user data');
        return {
            ...a,
            isAuthenticated: false,
            token: null,
            tokenExpires: null,
            user: null
        };
    });
    
    console.log('🢄[AUTH] - Redirecting to login page from auth.svelte.ts');
    goto('/login');
    console.log('🢄[AUTH] === LOGOUT COMPLETE ===');
}

export function isTokenExpired(tokenExpires: Date | null): boolean {
    if (!tokenExpires) return true;
    
    const now = new Date();
    const expiry = new Date(tokenExpires);
    
    // Add 30 second buffer to handle slight time differences
    const buffer = 30 * 1000;
    
    return expiry.getTime() - buffer <= now.getTime();
}

export function checkTokenValidity(): boolean {
    const authState = get(auth);
    
    if (!authState.token || !authState.tokenExpires) {
        console.log('🢄[AUTH] No token or expiry date found');
        return false;
    }
    
    if (isTokenExpired(authState.tokenExpires)) {
        console.log('🢄[AUTH] Token has expired, logging out');
        logout('Token expired');
        return false;
    }
    
    return true;
}

export async function authenticatedFetch(url: string, options: RequestInit = {}): Promise<Response> {
    // Check token validity before making request
    if (!checkTokenValidity()) {
        throw new Error('Token expired. Please log in again.');
    }
    
    const authState = get(auth);
    
    // Add authorization header
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${authState.token}`
    };
    
    try {
        const response = await fetch(url, {
            ...options,
            headers
        });
        
        // Handle 401 Unauthorized responses
        if (response.status === 401) {
            console.log('🢄[AUTH] Received 401 response, token may be invalid');
            logout('Authentication failed');
            throw new Error('Authentication failed. Please log in again.');
        }
        
        return response;
    } catch (error) {
        // Re-throw the error for the caller to handle
        throw error;
    }
}

export async function fetchUserData() {
    const a = get(auth);
    
    console.log('🢄[AUTH] === FETCHING USER DATA ===');
    console.log('🢄[AUTH] - Current auth state:');
    console.log('🢄[AUTH]   - isAuthenticated:', a.isAuthenticated);
    console.log('🢄[AUTH]   - Has token:', !!a.token);
    console.log('🢄[AUTH]   - Has user:', !!a.user);
    
    // If we don't have a token in the auth store, try to get it from localStorage
    const tokenToUse = a.token || localStorage.getItem('token');
    console.log('🢄[AUTH] - Token to use:', tokenToUse ? 'exists' : 'none');
    if (tokenToUse) {
        console.log('🢄[AUTH]2   - Token preview:', tokenToUse.substring(0, 10) + '...');
    }
    
    if (!tokenToUse) {
        console.error('🢄[AUTH] NO TOKEN AVAILABLE to fetch user data');
        return null;
    }
    
    try {
        console.log('🢄[AUTH] Making API request to /api/auth/me');
        const response = await fetch(backendUrl+'/auth/me', {
            headers: {
                'Authorization': `Bearer ${tokenToUse}`
            }
        });
        
        console.log('🢄[AUTH] - API response status:', response.status);
        
        if (!response.ok) {
            console.error('🢄[AUTH] API request failed:', response.status, response.statusText);
            
            if (response.status === 401) {
                console.log('🢄[AUTH] UNAUTHORIZED: Token expired or invalid, logging out');
                logout();
            }
            return null;
        }
        
        const userData = await response.json();
        console.log('🢄[AUTH] USER DATA FETCHED SUCCESSFULLY:');
        console.log('🢄[AUTH] - User ID:', userData.id);
        console.log('🢄[AUTH] - Username:', userData.username);
        console.log('🢄[AUTH] - Email:', userData.email);
        
        // If we successfully got user data, ensure isAuthenticated is true and update token
        console.log('🢄[AUTH] Updating auth store with user data');
        auth.update(a => {
            console.log('🢄[AUTH] - Setting isAuthenticated to true');
            console.log('🢄[AUTH] - Updating token and user data');
            return {
                ...a,
                isAuthenticated: true,
                token: tokenToUse,
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires') + 'Z') : null,
                user: userData
            };
        });
        
        // Fetch user photos
        console.log('🢄[AUTH] Fetching user photos');
        await fetchUserPhotos();
        
        console.log('🢄[AUTH] === USER DATA FETCH COMPLETE ===');
        return userData;
    } catch (error) {
        console.error('🢄[AUTH] ERROR FETCHING USER DATA:', error);
        return null;
    }
}

export async function fetchUserPhotos() {
    const a = get(auth);
    
    // If we're not authenticated, don't try to fetch photos
    if (!a.isAuthenticated) return null;
    
    // If we don't have a token in the auth store, try to get it from localStorage
    const tokenToUse = a.token || localStorage.getItem('token');
    if (!tokenToUse) {
        console.error('🢄[AUTH] No token available to fetch user photos');
        return null;
    }
    
    try {
        const response = await fetch(backendUrl+'/photos', {
            headers: {
                'Authorization': `Bearer ${tokenToUse}`
            }
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // Token is invalid, log out
                logout();
            }
            return null;
        }
        
        const photos = await response.json();
        
        // Update shared store with user photos
        userPhotos.set(photos);
        
        // If we used a token from localStorage, update the auth store
        if (!a.token && tokenToUse) {
            auth.update(state => ({
                ...state,
                token: tokenToUse,
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires') + 'Z') : null
            }));
        }
        
        return photos;
    } catch (error) {
        console.error('🢄[AUTH] Error fetching user photos:', error);
        return null;
    }
}

// Check token validity on app start
export function checkAuth() {
    const a = get(auth);
    
    console.log('🢄[AUTH] === CHECKING AUTH STATE ===');
    console.log('🢄[AUTH] - isAuthenticated:', a.isAuthenticated);
    console.log('🢄[AUTH] - Has token:', !!a.token);
    console.log('🢄[AUTH] - Has user:', !!a.user);
    if (a.token) {
        console.log('🢄[AUTH]3 - Token preview:', a.token.substring(0, 10) + '...');
    }
    if (a.tokenExpires) {
        console.log('🢄[AUTH] - Token expires:', a.tokenExpires);
        console.log('🢄[AUTH] - Current time:', new Date());
        console.log('🢄[AUTH] - Time until expiry (ms):', a.tokenExpires.getTime() - new Date().getTime());
    }
    if (a.user) {
        console.log('🢄[AUTH] - User ID:', a.user.id);
        console.log('🢄[AUTH] - Username:', a.user.username);
    }
    
    // If we have a token, try to fetch user data regardless of isAuthenticated flag
    if (a.token) {
        if (a.tokenExpires && new Date() > new Date(a.tokenExpires)) {
            // Token expired
            console.log('🢄[AUTH] TOKEN EXPIRED, logging out');
            console.log('🢄[AUTH] - Token expiry:', a.tokenExpires);
            console.log('🢄[AUTH] - Current time:', new Date());
            logout();
        } else {
            // Token exists, fetch user data and photos
            console.log('🢄[AUTH] Token valid, fetching user data');
            fetchUserData();
        }
    } else if (a.user) {
        // We have user data but no token - try to recover from localStorage
        console.log('🢄[AUTH] INCONSISTENT STATE: User data exists but no token');
        const storedToken = localStorage.getItem('token');
        console.log('🢄[AUTH] - Token in localStorage:', !!storedToken);
        
        if (storedToken) {
            console.log('🢄[AUTH] Found token in localStorage, restoring it');
            console.log('🢄[AUTH]4 - Token preview:', storedToken.substring(0, 10) + '...');
            
            const storedExpiry = localStorage.getItem('token_expires');
            console.log('🢄[AUTH] - Token expiry in localStorage:', storedExpiry);
            
            auth.update(state => ({
                ...state,
                isAuthenticated: true,
                token: storedToken,
                tokenExpires: storedExpiry ? new Date(storedExpiry + 'Z') : null
            }));
            
            // Now that we have a token, fetch user data again
            console.log('🢄[AUTH] Fetching user data with restored token');
            setTimeout(() => fetchUserData(), 100);
        } else {
            // No token in localStorage either, this is truly inconsistent
            console.log('🢄[AUTH] NO TOKEN IN LOCALSTORAGE, truly inconsistent state');
            
            if (a.isAuthenticated) {
                // We're marked as authenticated but have no token, this is wrong
                console.log('🢄[AUTH] Marked as authenticated but no token, logging out');
                logout();
            }
        }
    } else if (a.isAuthenticated && !a.user) {
        // We think we're authenticated but have no user data - fix this inconsistency
        console.log('🢄[AUTH] INCONSISTENT STATE: Authenticated but no user data');
        
        const storedToken = localStorage.getItem('token');
        console.log('🢄[AUTH] - Token in localStorage:', !!storedToken);
        
        if (storedToken) {
            console.log('🢄[AUTH] Found token in localStorage, restoring it');
            console.log('🢄[AUTH]5 - Token preview:', storedToken.substring(0, 10) + '...');
            
            const storedExpiry = localStorage.getItem('token_expires');
            console.log('🢄[AUTH] - Token expiry in localStorage:', storedExpiry);
            
            auth.update(state => ({
                ...state,
                token: storedToken,
                tokenExpires: storedExpiry ? new Date(storedExpiry + 'Z') : null
            }));
            
            // Now that we have a token, fetch user data
            console.log('🢄[AUTH] Fetching user data with restored token');
            setTimeout(() => fetchUserData(), 100);
        } else {
            // No token in localStorage either, this is truly inconsistent
            console.log('🢄[AUTH] NO TOKEN IN LOCALSTORAGE, logging out');
            logout();
        }
    } else {
        // No token in auth store - check localStorage for token
        console.log('🢄[AUTH] NO TOKEN IN AUTH STORE - checking localStorage');
        const storedToken = localStorage.getItem('token');
        const storedExpiry = localStorage.getItem('token_expires');
        
        if (storedToken && storedExpiry) {
            const expiry = new Date(storedExpiry + 'Z');
            const now = new Date();
            
            console.log('🢄[AUTH] Found token in localStorage:');
            console.log('🢄[AUTH]6 - Token preview:', storedToken.substring(0, 10) + '...');
            console.log('🢄[AUTH] - Token expiry:', expiry);
            console.log('🢄[AUTH] - Current time:', now);
            console.log('🢄[AUTH] - Token valid:', expiry > now);
            
            if (expiry > now) {
                console.log('🢄[AUTH] Token is valid, restoring auth state');
                auth.update(state => ({
                    ...state,
                    isAuthenticated: true,
                    token: storedToken,
                    tokenExpires: expiry
                }));
                
                // Fetch user data with the restored token
                console.log('🢄[AUTH] Fetching user data with restored token from localStorage');
                setTimeout(() => fetchUserData(), 100);
            } else {
                console.log('🢄[AUTH] Token in localStorage is expired, clearing it');
                localStorage.removeItem('token');
                localStorage.removeItem('token_expires');
            }
        } else {
            console.log('🢄[AUTH] No token in localStorage either - user is not authenticated');
        }
    }
    
    console.log('🢄[AUTH] === AUTH CHECK COMPLETE ===');
}

// Debug function to log auth state
export function debugAuth() {
    const a = get(auth);
    console.log('🢄[AUTH] Auth state:', {
        isAuthenticated: a.isAuthenticated,
        hasToken: !!a.token,
        tokenExpires: a.tokenExpires,
        hasUser: !!a.user,
        user: a.user
    });
    return a;
}
