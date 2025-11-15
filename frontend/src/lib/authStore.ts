import { writable, get } from 'svelte/store';

export interface User {
    id: string;
    username: string;
    email: string;
    [key: string]: unknown;
}

export interface AuthState {
    is_authenticated: boolean;
    user: User | null;
    refresh_status: 'idle' | 'refreshing' | 'retrying' | 'failed';
    refresh_attempt?: number;
}

// Create the auth store
export const auth = writable<AuthState>({
    is_authenticated: false,
    user: null,
    refresh_status: 'idle',
    refresh_attempt: undefined
});

// Create a userId store that only changes when the actual user ID changes
export const userId = writable<string | null>(null);

// Subscribe to auth changes and update userId only when it actually changes
auth.subscribe((authState) => {
    const currentUserId = authState.is_authenticated && authState.user ? authState.user.id : null;
    if (get(userId) !== currentUserId) {
        userId.set(currentUserId);
    }
});