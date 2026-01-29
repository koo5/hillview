import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock $lib/tauri BEFORE importing authCallback
vi.mock('$lib/tauri', () => ({
    TAURI: true,
    BROWSER: false,
    TAURI_MOBILE: true,
    TAURI_DESKTOP: false,
    isTauriAvailable: () => true
}));

// Mock Tauri API
vi.mock('@tauri-apps/api/core', () => ({
    invoke: vi.fn()
}));

// Mock SvelteKit modules
vi.mock('$app/environment', () => ({
    browser: true
}));

// Mock auth completion
vi.mock('$lib/auth.svelte', () => ({
    completeAuthentication: vi.fn()
}));

// Mock navigation
vi.mock('$lib/navigation.svelte', () => ({
    myGoto: vi.fn().mockResolvedValue(undefined)
}));

// Import after mocks are set up
const { invoke } = await import('@tauri-apps/api/core');
const { completeAuthentication } = await import('$lib/auth.svelte');
const mockInvoke = vi.mocked(invoke);
const mockCompleteAuth = vi.mocked(completeAuthentication);

import {
    handleAuthCallback,
    getStoredToken,
    clearStoredToken,
    hasValidAuth
} from '$lib/authCallback';

describe('Tauri Auth Token Storage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('getStoredToken', () => {
        it('should return token when available', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: 'stored.jwt.token'
            });

            const result = await getStoredToken();

            expect(result).toBe('stored.jwt.token');
            expect(mockInvoke).toHaveBeenCalledWith('plugin:hillview|get_auth_token');
        });

        it('should return null when no token available', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: null
            });

            const result = await getStoredToken();

            expect(result).toBe(null);
        });

        it('should throw on invoke error', async () => {
            mockInvoke.mockRejectedValueOnce(new Error('Tauri error'));

            await expect(getStoredToken()).rejects.toThrow('Tauri error');
        });
    });

    describe('clearStoredToken', () => {
        it('should clear token successfully', async () => {
            mockInvoke.mockResolvedValueOnce({ success: true });

            const result = await clearStoredToken();

            expect(result).toBe(true);
            expect(mockInvoke).toHaveBeenCalledWith('plugin:hillview|clear_auth_token');
        });

        it('should return false on failure', async () => {
            mockInvoke.mockResolvedValueOnce({ success: false });

            const result = await clearStoredToken();

            expect(result).toBe(false);
        });
    });

    describe('hasValidAuth', () => {
        it('should return true for valid unexpired token', async () => {
            const futureDate = new Date(Date.now() + 3600000).toISOString(); // 1 hour from now
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: 'header.payload.signature',
                expires_at: futureDate
            });

            const result = await hasValidAuth();

            expect(result).toBe(true);
        });

        it('should return false when no token exists', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: null
            });

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });

        it('should return false for expired token', async () => {
            const pastDate = '2020-01-01T00:00:00Z';
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: 'header.payload.signature',
                expires_at: pastDate
            });

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });

        it('should return false for invalid token format', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: 'invalid-token-format' // Not a valid JWT (needs 3 parts)
            });

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });

        it('should return false on invoke failure', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: false,
                error: 'Storage error'
            });

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });
    });
});

describe('Tauri Deep Link Auth Callback', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should handle valid auth callback with all required parameters', async () => {
        const futureDate = new Date(Date.now() + 3600000).toISOString();
        const refreshExpiry = new Date(Date.now() + 86400000).toISOString();
        const mockUrl = `cz.hillview://auth?token=jwt.token.here&expires_at=${futureDate}&refresh_token=refresh.token&refresh_token_expires_at=${refreshExpiry}`;

        mockCompleteAuth.mockResolvedValueOnce(true);

        const result = await handleAuthCallback(mockUrl);

        expect(result).toBe(true);
        expect(mockCompleteAuth).toHaveBeenCalledWith(
            expect.objectContaining({
                access_token: 'jwt.token.here',
                expires_at: futureDate,
                refresh_token: 'refresh.token',
                refresh_token_expires_at: refreshExpiry
            }),
            'oauth'
        );
    });

    it('should return false for invalid URL scheme', async () => {
        const mockUrl = 'https://example.com/auth?token=jwt.token.here';

        const result = await handleAuthCallback(mockUrl);

        expect(result).toBe(false);
        expect(mockCompleteAuth).not.toHaveBeenCalled();
    });

    it('should return false when missing required parameters', async () => {
        const mockUrl = 'cz.hillview://auth?token=jwt.token.here'; // Missing expires_at and refresh_token_expires_at

        const result = await handleAuthCallback(mockUrl);

        expect(result).toBe(false);
    });

    it('should return false when authentication completion fails', async () => {
        const futureDate = new Date(Date.now() + 3600000).toISOString();
        const refreshExpiry = new Date(Date.now() + 86400000).toISOString();
        const mockUrl = `cz.hillview://auth?token=jwt.token.here&expires_at=${futureDate}&refresh_token_expires_at=${refreshExpiry}`;

        mockCompleteAuth.mockResolvedValueOnce(false);

        const result = await handleAuthCallback(mockUrl);

        expect(result).toBe(false);
    });

    it('should handle OAuth error responses', async () => {
        const errorUrl = 'cz.hillview://auth?error=access_denied&error_description=User%20denied%20access';

        const result = await handleAuthCallback(errorUrl);

        expect(result).toBe(false);
        expect(mockCompleteAuth).not.toHaveBeenCalled();
    });
});
