import { describe, it, expect, vi, beforeEach } from 'vitest';

const kotlinMessageQueueMock = vi.hoisted(() => ({ on: vi.fn() }));
const invokeMock = vi.hoisted(() => vi.fn());
const getAuthGenerationMock = vi.hoisted(() => vi.fn(() => 0));

vi.mock('@tauri-apps/api/core', () => ({ invoke: invokeMock }));
vi.mock('$lib/KotlinMessageQueue', () => ({ kotlinMessageQueue: kotlinMessageQueueMock }));
vi.mock('$lib/auth.svelte', () => ({ logout: vi.fn(), getAuthGeneration: getAuthGenerationMock }));

import { AndroidTokenManager } from '$lib/androidTokenManager';
import { logout } from '$lib/auth.svelte';

const logoutMock = vi.mocked(logout);

// The 'auth-expired' handler the manager registers on the durable Kotlin→JS queue.
function authExpiredHandler(): () => Promise<void> {
    const call = kotlinMessageQueueMock.on.mock.calls.find((c) => c[0] === 'auth-expired');
    return call![1] as () => Promise<void>;
}

beforeEach(() => {
    vi.clearAllMocks();
    getAuthGenerationMock.mockReturnValue(0);
});

describe('AndroidTokenManager — native session expiry', () => {
    it('registers an auth-expired handler on construction', () => {
        new AndroidTokenManager();
        expect(kotlinMessageQueueMock.on).toHaveBeenCalledWith('auth-expired', expect.any(Function));
    });

    it('logs out (in lockstep with native) when no valid token remains, tagged with the current generation', async () => {
        new AndroidTokenManager();
        getAuthGenerationMock.mockReturnValue(5);
        invokeMock.mockResolvedValue({ success: true, token: null }); // native cleared the session

        await authExpiredHandler()();

        // Generation-tagged so logout()'s stale-guard can suppress it if a re-login intervened.
        expect(logoutMock).toHaveBeenCalledWith('Session expired (native)', { generation: 5 });
    });

    it('snapshots the generation at receipt, before the async token re-check (closes the re-login TOCTOU)', async () => {
        new AndroidTokenManager();
        getAuthGenerationMock.mockReturnValue(7); // generation at the moment auth-expired arrives
        // Simulate a re-login bumping the generation DURING the getValidToken() re-check.
        invokeMock.mockImplementation(async () => {
            getAuthGenerationMock.mockReturnValue(8);
            return { success: true, token: null };
        });

        await authExpiredHandler()();

        // logout is tagged with the receipt-time generation (7), not the post-re-login 8,
        // so logout()'s guard (7 !== current 8) suppresses tearing down the fresh session.
        expect(logoutMock).toHaveBeenCalledWith('Session expired (native)', { generation: 7 });
    });

    it('does NOT log out if native already has a valid token again (re-login race)', async () => {
        new AndroidTokenManager();
        invokeMock.mockResolvedValue({ success: true, token: 'fresh-token' }); // re-login replaced session

        await authExpiredHandler()();

        expect(logoutMock).not.toHaveBeenCalled();
    });

    it('does not throw if the token re-check fails', async () => {
        new AndroidTokenManager();
        invokeMock.mockRejectedValue(new Error('bridge error'));

        // getValidToken swallows errors → returns null → logs out; the handler must not reject.
        await expect(authExpiredHandler()()).resolves.toBeUndefined();
    });
});
