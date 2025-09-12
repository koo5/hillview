import { writable, get } from 'svelte/store';

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
    refreshStatus: 'idle' | 'refreshing' | 'retrying' | 'failed';
    refreshAttempt?: number;
}

// Create the auth store
export const auth = writable<AuthState>({
    isAuthenticated: false,
    user: null,
    refreshStatus: 'idle',
    refreshAttempt: undefined
});

// Create a userId store that only changes when the actual user ID changes
export const userId = writable<string | null>(null);

// Subscribe to auth changes and update userId only when it actually changes
auth.subscribe((authState) => {
    const currentUserId = authState.isAuthenticated && authState.user ? authState.user.id : null;
    if (get(userId) !== currentUserId) {
        userId.set(currentUserId);
    }
});