import { writable, get } from 'svelte/store';
import { goto } from "$app/navigation";
import { userPhotos } from './stores';

// Check for existing token
const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
const tokenExpires = typeof localStorage !== 'undefined' ? localStorage.getItem('token_expires') : null;
const isAuthenticated = token && tokenExpires && new Date(tokenExpires) > new Date();

// Auth store
export const auth = writable({
    isAuthenticated: isAuthenticated,
    token: token,
    tokenExpires: tokenExpires ? new Date(tokenExpires) : null,
    user: null
});

// If we have a token but isAuthenticated is false, this might be a bug
// Let's check the token validity immediately
if (token && !isAuthenticated && tokenExpires) {
    console.log('Token exists but isAuthenticated is false, checking token validity');
    const expiry = new Date(tokenExpires);
    if (expiry > new Date()) {
        console.log('Token is still valid, setting isAuthenticated to true');
        auth.update(state => ({
            ...state,
            isAuthenticated: true
        }));
    }
}

// Auth functions
export async function login(username: string, password: string) {
    try {
        console.log('Logging in with:', { username });
        const response = await fetch('http://localhost:8089/api/auth/token', {
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
        
        console.log('Login successful, token received:', data);
        
        // Store token
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('token_expires', data.expires_at);
        
        // Update auth store with token info first
        auth.update(a => {
            console.log('Setting token and isAuthenticated to true');
            return {
                ...a,
                isAuthenticated: true,
                token: data.access_token,
                tokenExpires: new Date(data.expires_at)
            };
        });
        
        // Fetch user data
        const userData = await fetchUserData();
        console.log('User data fetched:', userData);
        
        // Ensure isAuthenticated is still true after fetching user data
        auth.update(a => {
            if (!a.isAuthenticated && a.user) {
                console.log('Fixing inconsistent state: user exists but not authenticated');
                return {
                    ...a,
                    isAuthenticated: true
                };
            }
            return a;
        });
        
        // Double-check auth state
        console.log('Auth state after login:', debugAuth());
        
        return true;
    } catch (error) {
        console.error('Login error:', error);
        return false;
    }
}

export async function register(email: string, username: string, password: string) {
    try {
        console.log('Registering user:', { email, username });
        const response = await fetch('http://localhost:8089/api/auth/register', {
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
            console.error('Registration error response:', errorText);
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
        console.error('Registration error:', error);
        return false;
    }
}

export async function oauthLogin(provider: string, code: string, redirectUri?: string) {
    try {
        const response = await fetch('http://localhost:8089/api/auth/oauth', {
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
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('token_expires', data.expires_at);
        
        // Update auth store
        auth.update(a => ({
            ...a,
            isAuthenticated: true,
            token: data.access_token,
            tokenExpires: new Date(data.expires_at)
        }));
        
        // Fetch user data
        await fetchUserData();
        
        return true;
    } catch (error) {
        console.error('OAuth login error:', error);
        return false;
    }
}

export function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('token_expires');
    
    auth.update(a => ({
        ...a,
        isAuthenticated: false,
        token: null,
        tokenExpires: null,
        user: null
    }));
    
    goto('/login');
}

export async function fetchUserData() {
    const a = get(auth);
    
    // If we don't have a token in the auth store, try to get it from localStorage
    const tokenToUse = a.token || localStorage.getItem('token');
    if (!tokenToUse) {
        console.error('No token available to fetch user data');
        return null;
    }
    
    try {
        const response = await fetch('http://localhost:8089/api/auth/me', {
            headers: {
                'Authorization': `Bearer ${tokenToUse}`
            }
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // Token expired or invalid
                logout();
            }
            return null;
        }
        
        const userData = await response.json();
        console.log('User data fetched successfully:', userData);
        
        // If we successfully got user data, ensure isAuthenticated is true and update token
        auth.update(a => {
            console.log('Updating auth store with user data, setting isAuthenticated to true');
            return {
                ...a,
                isAuthenticated: true,
                token: tokenToUse,
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires')) : null,
                user: userData
            };
        });
        
        // Fetch user photos
        await fetchUserPhotos();
        
        return userData;
    } catch (error) {
        console.error('Error fetching user ', error);
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
        console.error('No token available to fetch user photos');
        return null;
    }
    
    try {
        const response = await fetch('http://localhost:8089/api/photos', {
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
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires')) : null
            }));
        }
        
        return photos;
    } catch (error) {
        console.error('Error fetching user photos:', error);
        return null;
    }
}

// Check token validity on app start
export function checkAuth() {
    const a = get(auth);
    
    console.log('Checking auth state:', a);
    
    // If we have a token, try to fetch user data regardless of isAuthenticated flag
    if (a.token) {
        if (a.tokenExpires && new Date() > new Date(a.tokenExpires)) {
            // Token expired
            console.log('Token expired, logging out');
            logout();
        } else {
            // Token exists, fetch user data and photos
            console.log('Token exists, fetching user data');
            fetchUserData();
        }
    } else if (a.user) {
        // We have user data but no token - try to recover from localStorage
        console.log('Inconsistent auth state: user data but no token, checking localStorage');
        const storedToken = localStorage.getItem('token');
        if (storedToken) {
            console.log('Found token in localStorage, restoring it');
            auth.update(state => ({
                ...state,
                isAuthenticated: true,
                token: storedToken,
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires')) : null
            }));
            // Now that we have a token, fetch user data again
            setTimeout(() => fetchUserData(), 100);
        } else {
            // No token in localStorage either, this is truly inconsistent
            console.log('No token in localStorage, this is truly inconsistent');
            if (a.isAuthenticated) {
                // We're marked as authenticated but have no token, this is wrong
                console.log('Marked as authenticated but have no token, logging out');
                logout();
            }
        }
    } else if (a.isAuthenticated && !a.user) {
        // We think we're authenticated but have no user data - fix this inconsistency
        console.log('Inconsistent auth state: authenticated but no user data');
        const storedToken = localStorage.getItem('token');
        if (storedToken) {
            console.log('Found token in localStorage, restoring it');
            auth.update(state => ({
                ...state,
                token: storedToken,
                tokenExpires: localStorage.getItem('token_expires') ? new Date(localStorage.getItem('token_expires')) : null
            }));
            // Now that we have a token, fetch user data
            setTimeout(() => fetchUserData(), 100);
        } else {
            // No token in localStorage either, this is truly inconsistent
            console.log('No token in localStorage, logging out');
            logout();
        }
    }
}

// Debug function to log auth state
export function debugAuth() {
    const a = get(auth);
    console.log('Auth state:', {
        isAuthenticated: a.isAuthenticated,
        hasToken: !!a.token,
        tokenExpires: a.tokenExpires,
        hasUser: !!a.user,
        user: a.user
    });
    return a;
}
