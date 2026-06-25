import { describe, it, expect, vi, beforeEach } from 'vitest';

const tokenManagerMock = vi.hoisted(() => ({ getValidToken: vi.fn() }));

vi.mock('$lib/tokenManagerFactory', () => ({ createTokenManager: () => tokenManagerMock }));
vi.mock('$lib/auth.svelte', () => ({
    auth: { subscribe: vi.fn(() => () => {}) },
    logout: vi.fn(),
    getAuthGeneration: vi.fn(() => 7),
}));
vi.mock('$lib/alertSystem.svelte', () => ({ showNetworkError: vi.fn() }));

import { HttpClient, TokenExpiredError } from '$lib/http';
import { TokenExpiredError as TokenManagerExpiredError } from '$lib/tokenManager';
import { logout } from '$lib/auth.svelte';
import { showNetworkError } from '$lib/alertSystem.svelte';

const logoutMock = vi.mocked(logout);
const showNetworkErrorMock = vi.mocked(showNetworkError);
const getValidToken = tokenManagerMock.getValidToken;

function resp(status: number, body: unknown = {}): Response {
    return {
        ok: status >= 200 && status < 300,
        status,
        statusText: `status ${status}`,
        json: async () => body,
        text: async () => JSON.stringify(body),
    } as unknown as Response;
}

let client: HttpClient;
beforeEach(() => {
    vi.clearAllMocks();
    client = new HttpClient('https://api.test');
});

describe('HttpClient — auth handling', () => {
    it('attaches the bearer token and returns the response on success', async () => {
        getValidToken.mockResolvedValue('tok');
        global.fetch = vi.fn().mockResolvedValue(resp(200));

        const r = await client.get('/x');

        expect(r.status).toBe(200);
        expect(vi.mocked(global.fetch).mock.calls[0][1]?.headers).toMatchObject({
            Authorization: 'Bearer tok',
        });
        expect(logoutMock).not.toHaveBeenCalled();
    });

    it('returns a 401 without logging out when no token was sent (anonymous request)', async () => {
        getValidToken.mockResolvedValue(null);
        global.fetch = vi.fn().mockResolvedValue(resp(401));

        const r = await client.get('/protected');

        expect(r.status).toBe(401);
        expect(logoutMock).not.toHaveBeenCalled();
        expect(global.fetch).toHaveBeenCalledTimes(1); // no retry
    });

    it('retries once with a fresh token after a 401 and returns the retried response', async () => {
        getValidToken.mockResolvedValueOnce('old').mockResolvedValueOnce('new');
        global.fetch = vi.fn().mockResolvedValueOnce(resp(401)).mockResolvedValueOnce(resp(200));

        const r = await client.get('/x');

        expect(r.status).toBe(200);
        expect(global.fetch).toHaveBeenCalledTimes(2);
        expect(vi.mocked(global.fetch).mock.calls[1][1]?.headers).toMatchObject({
            Authorization: 'Bearer new',
        });
        expect(logoutMock).not.toHaveBeenCalled();
    });

    it('surfaces a connection error (status 0), NOT a logout, when the post-401 refresh fails transiently', async () => {
        // token present; the forced refresh returns null → transient (session kept)
        getValidToken.mockResolvedValueOnce('old').mockResolvedValueOnce(null);
        global.fetch = vi.fn().mockResolvedValueOnce(resp(401));

        await expect(client.get('/x')).rejects.toMatchObject({ status: 0 });
        expect(showNetworkErrorMock).toHaveBeenCalled();
        expect(logoutMock).not.toHaveBeenCalled();
    });

    it('logs out (generation-tagged) and throws on a terminal post-401 refresh failure', async () => {
        getValidToken.mockResolvedValueOnce('old').mockRejectedValueOnce(new TokenManagerExpiredError());
        global.fetch = vi.fn().mockResolvedValueOnce(resp(401));

        await expect(client.get('/x')).rejects.toBeInstanceOf(TokenExpiredError);
        expect(logoutMock).toHaveBeenCalledWith('Session expired', { generation: 7 });
    });

    it('logs out and throws (without fetching) when the initial token fetch fails terminally', async () => {
        getValidToken.mockRejectedValueOnce(new TokenManagerExpiredError());
        global.fetch = vi.fn();

        await expect(client.get('/x')).rejects.toBeInstanceOf(TokenExpiredError);
        expect(logoutMock).toHaveBeenCalled();
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
