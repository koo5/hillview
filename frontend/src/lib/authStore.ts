import { writable, derived, get } from 'svelte/store';

export interface User {
    id: string;
    username: string;
    email: string;
    [key: string]: unknown;
}

export interface AuthState {
    is_authenticated: boolean;
    checked: boolean;
    user: User | null;
    /**
     * Loading state of the user profile, which is fetched by a separate request and
     * is therefore independent of is_authenticated. A view that needs the profile
     * should show a spinner on 'loading', a retry on 'error', and content on 'loaded'
     * — NOT treat a missing user as "logged out" (the auth truth is is_authenticated).
     */
    userStatus: 'idle' | 'loading' | 'loaded' | 'error';
    refresh_status: 'idle' | 'refreshing' | 'retrying' | 'failed';
    refresh_attempt?: number;
}

// Create the auth store
export const auth = writable<AuthState>({
    is_authenticated: false,
    checked: false,
    user: null,
    userStatus: 'idle',
    refresh_status: 'idle',
    refresh_attempt: undefined
});

// Authenticated but the profile (a separate request) isn't loaded yet and is still
// being fetched — the "show a spinner" window. Drives <Loadable> at auth-gated views.
export const profileLoading = derived(
    auth,
    ($a) => $a.is_authenticated && !$a.user && $a.userStatus !== 'error',
);

// Authenticated but the profile fetch failed — the "show a retry" state. Lets a view
// surface a retry instead of spinning forever when /auth/me is failing.
export const profileError = derived(
    auth,
    ($a) => $a.is_authenticated && !$a.user && $a.userStatus === 'error',
);

// Create a userId store that only changes when the actual user ID changes
export const userId = writable<string | null>(null);

// Subscribe to auth changes and update userId only when it actually changes
auth.subscribe((authState) => {
    const currentUserId = authState.is_authenticated && authState.user ? authState.user.id : null;
    if (get(userId) !== currentUserId) {
        userId.set(currentUserId);
    }
});