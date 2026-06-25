import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock webTokenManager's collaborators so we can drive the refresh outcome via fetch
// and spy on logout.
vi.mock('$lib/http', () => ({ http: {} }));
vi.mock('$lib/clientCrypto', () => ({ clientCrypto: {} }));
vi.mock('$lib/auth.svelte', () => ({
    logout: vi.fn(),
    fetchUserData: vi.fn(),
    getAuthGeneration: vi.fn(() => 1),
    bumpAuthGeneration: vi.fn(),
}));

const authStorageMock = vi.hoisted(() => ({
    onAuthChange: vi.fn(),
    getTokenData: vi.fn(),
    saveTokenData: vi.fn().mockResolvedValue(undefined),
    clearTokens: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('$lib/browser/authStorage', () => ({ authStorage: authStorageMock }));

import { WebTokenManager } from '$lib/webTokenManager';
import { logout, bumpAuthGeneration, fetchUserData } from '$lib/auth.svelte';
import { TokenExpiredError } from '$lib/tokenManager';

const logoutMock = vi.mocked(logout);
const bumpMock = vi.mocked(bumpAuthGeneration);
const fetchUserDataMock = vi.mocked(fetchUserData);

function expiredTokenData() {
    const now = Date.now();
    return {
        access_token: 'old-access',
        refresh_token: 'refresh-token',
        expires_at: now - 60_000, // access token already expired
        refresh_token_expires: now + 86_400_000, // refresh token valid for another day
    };
}

function validTokenData() {
    const now = Date.now();
    return {
        access_token: 'fresh-access',
        refresh_token: 'refresh-token',
        expires_at: now + 60 * 60_000, // access token valid for an hour
        refresh_token_expires: now + 30 * 86_400_000, // refresh token well beyond the renewal buffer
    };
}

beforeEach(() => {
    vi.clearAllMocks();
    authStorageMock.getTokenData.mockResolvedValue(expiredTokenData());
});

describe('WebTokenManager refresh: transient vs terminal', () => {
    it('keeps the session on a transient failure (returns null, never logs out)', async () => {
        vi.useFakeTimers();
        try {
            // Every refresh attempt aborts (timeout) — a connectivity failure.
            const abortError = Object.assign(new Error('aborted'), { name: 'AbortError' });
            (global.fetch as unknown) = vi.fn().mockRejectedValue(abortError);

            const mgr = new WebTokenManager();
            await mgr.init();

            const pending = mgr.getValidToken();
            // Drive the 1s + 2s retry backoffs to completion.
            await vi.advanceTimersByTimeAsync(10_000);
            const token = await pending;

            expect(token).toBeNull();
            expect(logoutMock).not.toHaveBeenCalled();
            // All three attempts were made.
            expect((global.fetch as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(3);
        } finally {
            vi.useRealTimers();
        }
    });

    it('logs out and throws on a terminal failure (server rejects the refresh token, 401)', async () => {
        (global.fetch as unknown) = vi.fn().mockResolvedValue({
            ok: false,
            status: 401,
            text: async () => 'invalid refresh token',
        });

        const mgr = new WebTokenManager();
        await mgr.init();

        await expect(mgr.getValidToken()).rejects.toBeInstanceOf(TokenExpiredError);
        expect(logoutMock).toHaveBeenCalledTimes(1);
    });
});

describe('WebTokenManager cross-tab auth sync', () => {
    // The constructor registers an onAuthChange handler; grab it to simulate
    // another tab's auth change.
    function onAuthChangeCb(): () => Promise<void> {
        return authStorageMock.onAuthChange.mock.calls.at(-1)![0];
    }

    it('bumps the auth generation when a login is synced from another tab', async () => {
        authStorageMock.getTokenData.mockResolvedValue(null); // this tab starts logged out
        const mgr = new WebTokenManager();
        await mgr.init();
        const onAuthChange = onAuthChangeCb();

        authStorageMock.getTokenData.mockResolvedValue(validTokenData()); // another tab logged in
        await onAuthChange();

        expect(bumpMock).toHaveBeenCalledTimes(1);
        expect(fetchUserDataMock).toHaveBeenCalled();
    });

    it('does NOT bump the generation for a cross-tab token refresh (already had tokens)', async () => {
        authStorageMock.getTokenData.mockResolvedValue(validTokenData()); // already logged in
        const mgr = new WebTokenManager();
        await mgr.init();
        const onAuthChange = onAuthChangeCb();

        authStorageMock.getTokenData.mockResolvedValue(validTokenData()); // still logged in (refresh)
        await onAuthChange();

        expect(bumpMock).not.toHaveBeenCalled();
    });

    it('does NOT bump the generation on a cross-tab logout', async () => {
        authStorageMock.getTokenData.mockResolvedValue(validTokenData());
        const mgr = new WebTokenManager();
        await mgr.init();
        const onAuthChange = onAuthChangeCb();

        authStorageMock.getTokenData.mockResolvedValue(null); // logged out elsewhere
        await onAuthChange();

        expect(bumpMock).not.toHaveBeenCalled();
    });
});

describe('WebTokenManager.recoverSessionIfNeeded', () => {
    type RecoverHandle = { recoverSessionIfNeeded(trigger: string): Promise<void> };

    function refreshResponse() {
        const now = Date.now();
        return {
            ok: true,
            status: 200,
            json: async () => ({
                access_token: 'new-access',
                token_type: 'bearer',
                expires_at: new Date(now + 60 * 60_000).toISOString(),
                refresh_token: 'new-refresh',
                refresh_token_expires_at: new Date(now + 30 * 86_400_000).toISOString(),
            }),
            text: async () => '',
        };
    }

    it('refreshes when the access token is expired and tokens are present', async () => {
        authStorageMock.getTokenData.mockResolvedValue(expiredTokenData());
        (global.fetch as unknown) = vi.fn().mockResolvedValue(refreshResponse());
        const mgr = new WebTokenManager();
        await mgr.init();

        await (mgr as unknown as RecoverHandle).recoverSessionIfNeeded('test');

        expect(global.fetch).toHaveBeenCalled();
    });

    it('is a no-op when the access token is still valid', async () => {
        authStorageMock.getTokenData.mockResolvedValue(validTokenData());
        (global.fetch as unknown) = vi.fn();
        const mgr = new WebTokenManager();
        await mgr.init();

        await (mgr as unknown as RecoverHandle).recoverSessionIfNeeded('test');

        expect(global.fetch).not.toHaveBeenCalled();
    });

    it('is a no-op when there are no tokens to recover', async () => {
        authStorageMock.getTokenData.mockResolvedValue(null);
        (global.fetch as unknown) = vi.fn();
        const mgr = new WebTokenManager();
        await mgr.init();

        await (mgr as unknown as RecoverHandle).recoverSessionIfNeeded('test');

        expect(global.fetch).not.toHaveBeenCalled();
    });
});
