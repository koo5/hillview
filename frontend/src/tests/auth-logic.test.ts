import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Disable the module-level auto-load subscription / reconnect listeners so the
// exported functions can be exercised in isolation.
vi.mock('$app/environment', () => ({ browser: false }));
vi.mock('$lib/http', () => ({ http: { get: vi.fn() } }));
vi.mock('$lib/navigation.svelte', () => ({ myGoto: vi.fn().mockResolvedValue(undefined) }));
vi.mock('$lib/alertSystem.svelte', () => ({ clearAlerts: vi.fn() }));
vi.mock('$lib/analytics', () => ({ identify: vi.fn() }));
vi.mock('$lib/simplePhotoWorker', () => ({ simplePhotoWorker: { invalidatePanoramaxHidden: vi.fn() } }));
vi.mock('$lib/tokenManagerFactory', () => ({
    createTokenManager: () => ({
        clearTokens: vi.fn().mockResolvedValue(undefined),
        getValidToken: vi.fn().mockResolvedValue(null),
    }),
}));

import { get } from 'svelte/store';
import { http } from '$lib/http';
import { myGoto } from '$lib/navigation.svelte';
import { auth, type AuthState, type User } from '$lib/authStore';
import {
    logout,
    getAuthGeneration,
    bumpAuthGeneration,
    fetchUserData,
    ensureUserLoaded,
    retryUserData,
} from '$lib/auth.svelte';

const httpGet = vi.mocked(http.get);
const SAMPLE_USER: User = { id: 'u1', username: 'bob', email: 'bob@example.com' };

function setAuth(partial: Partial<AuthState>): void {
    auth.set({
        is_authenticated: false,
        checked: false,
        user: null,
        userStatus: 'idle',
        refresh_status: 'idle',
        refresh_attempt: undefined,
        ...partial,
    });
}

function okResponse(user: User) {
    return { ok: true, json: async () => user } as unknown as Response;
}
function errorResponse(status = 500) {
    return { ok: false, status, statusText: 'error' } as unknown as Response;
}

beforeEach(() => {
    vi.clearAllMocks();
    setAuth({});
});

// Let any fire-and-forget fetch settle so the module-level dedup promise clears
// before the next test.
afterEach(async () => {
    await new Promise((r) => setTimeout(r, 0));
});

describe('auth generation guard', () => {
    it('ignores a logout requested by a stale generation (after a re-login bumped it)', async () => {
        setAuth({ is_authenticated: true, user: SAMPLE_USER, userStatus: 'loaded', checked: true });
        const staleGen = getAuthGeneration();
        bumpAuthGeneration(); // simulate completeAuthentication establishing a new session

        await logout('stale request', { generation: staleGen });

        expect(get(auth).is_authenticated).toBe(true);
        expect(get(auth).user).toEqual(SAMPLE_USER);
        expect(myGoto).not.toHaveBeenCalled();
    });

    it('proceeds for a logout carrying the current generation', async () => {
        setAuth({ is_authenticated: true, user: SAMPLE_USER, userStatus: 'loaded', checked: true });
        const gen = getAuthGeneration();

        await logout('real', { generation: gen });

        expect(get(auth).is_authenticated).toBe(false);
        expect(get(auth).user).toBeNull();
        expect(get(auth).userStatus).toBe('idle');
        expect(myGoto).toHaveBeenCalledWith('/login');
    });

    it('proceeds for a user-initiated logout (no generation passed)', async () => {
        setAuth({ is_authenticated: true, user: SAMPLE_USER, userStatus: 'loaded' });

        await logout('user clicked logout');

        expect(get(auth).is_authenticated).toBe(false);
        expect(myGoto).toHaveBeenCalledWith('/login');
    });

    it('bumpAuthGeneration increments the generation', () => {
        const before = getAuthGeneration();
        bumpAuthGeneration();
        expect(getAuthGeneration()).toBe(before + 1);
    });
});

describe('user profile loading', () => {
    it('fetchUserData goes idle → loaded and sets the user on success', async () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'idle' });
        httpGet.mockResolvedValue(okResponse(SAMPLE_USER));

        await fetchUserData();

        expect(get(auth).user).toMatchObject({ id: 'u1' });
        expect(get(auth).userStatus).toBe('loaded');
    });

    it('fetchUserData marks userStatus error on failure when no profile is loaded', async () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'idle' });
        httpGet.mockResolvedValue(errorResponse());

        await fetchUserData();

        expect(get(auth).user).toBeNull();
        expect(get(auth).userStatus).toBe('error');
    });

    it('a failed background refresh keeps the existing profile and loaded status', async () => {
        setAuth({ is_authenticated: true, user: SAMPLE_USER, userStatus: 'loaded' });
        httpGet.mockResolvedValue(errorResponse());

        await fetchUserData();

        expect(get(auth).user).toEqual(SAMPLE_USER);
        expect(get(auth).userStatus).toBe('loaded');
    });

    it('fetchUserData dedupes concurrent calls', async () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'idle' });
        let resolveGet!: (r: Response) => void;
        httpGet.mockReturnValue(new Promise<Response>((r) => { resolveGet = r; }));

        const p1 = fetchUserData();
        const p2 = fetchUserData();

        expect(httpGet).toHaveBeenCalledTimes(1);

        resolveGet(okResponse(SAMPLE_USER));
        await Promise.all([p1, p2]);

        expect(get(auth).userStatus).toBe('loaded');
    });

    it('ensureUserLoaded fetches when authenticated, missing profile, and idle', () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'idle' });
        httpGet.mockResolvedValue(okResponse(SAMPLE_USER));

        ensureUserLoaded();

        expect(httpGet).toHaveBeenCalledTimes(1);
    });

    it('ensureUserLoaded does NOT fetch from the error state (no retry loop)', () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'error' });

        ensureUserLoaded();

        expect(httpGet).not.toHaveBeenCalled();
    });

    it('ensureUserLoaded does NOT fetch when unauthenticated', () => {
        setAuth({ is_authenticated: false, user: null, userStatus: 'idle' });

        ensureUserLoaded();

        expect(httpGet).not.toHaveBeenCalled();
    });

    it('retryUserData fetches even from the error state', () => {
        setAuth({ is_authenticated: true, user: null, userStatus: 'error' });
        httpGet.mockResolvedValue(okResponse(SAMPLE_USER));

        retryUserData();

        expect(httpGet).toHaveBeenCalledTimes(1);
    });
});
