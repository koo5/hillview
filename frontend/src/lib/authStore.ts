import { writable } from 'svelte/store';

export interface User {
    id: string;
    username: string;
    email: string;
    auto_upload_enabled?: boolean;
    [key: string]: unknown;
}

export interface AuthState {
    isAuthenticated: boolean;
    user: User | null;
}

// Create the auth store
export const auth = writable<AuthState>({
    isAuthenticated: false,
    user: null
});