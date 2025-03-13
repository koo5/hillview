import { writable, get } from 'svelte/store';
import { goto } from "$app/navigation";

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
    if (!a.isAuthenticated || !a.token) return null;
    
    try {
        const response = await fetch('http://localhost:8089/api/auth/me', {
            headers: {
                'Authorization': `Bearer ${a.token}`
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
        
        auth.update(a => ({
            ...a,
            user: userData
        }));
        
        return userData;
    } catch (error) {
        console.error('Error fetching user ', error);
        return null;
    }
}

// Check token validity on app start
export function checkAuth() {
    const a = get(auth);
    if (a.isAuthenticated && a.tokenExpires) {
        if (new Date() > a.tokenExpires) {
            // Token expired
            logout();
        } else {
            // Token valid, fetch user data
            fetchUserData();
        }
    }
}
