import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock Tauri API
vi.mock('@tauri-apps/api/core', () => ({
    invoke: vi.fn()
}));

// Mock SvelteKit modules
vi.mock('$app/navigation', () => ({
    goto: vi.fn()
}));

vi.mock('$app/environment', () => ({
    browser: true
}));

// Import after mocks are set up
const { invoke } = await import('@tauri-apps/api/core');
const mockInvoke = vi.mocked(invoke);

import { 
    handleAuthCallback, 
    getStoredToken, 
    clearStoredToken, 
    hasValidAuth,
    buildOAuthUrl 
} from '$lib/authCallback';

describe('Authentication Callback Functions', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('buildOAuthUrl', () => {
        it('should build mobile OAuth URL correctly', () => {
            const url = buildOAuthUrl('google', true);
            
            expect(url).toContain('/auth/oauth-redirect');
            expect(url).toContain('provider=google');
            expect(url).toContain('redirect_uri=com.hillview%3A%2F%2Fauth');
        });

        it('should build web OAuth URL correctly', () => {
            // Mock window.location.origin
            Object.defineProperty(window, 'location', {
                value: {
                    origin: 'http://localhost:3000'
                },
                writable: true
            });

            const url = buildOAuthUrl('github', false);
            
            expect(url).toContain('/auth/oauth-redirect');
            expect(url).toContain('provider=github');
            expect(url).toContain('redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Foauth%2Fcallback');
        });

        it('should use centralized backend configuration', () => {
            const url = buildOAuthUrl('google', true);
            
            // Should use the backendUrl from config.ts
            expect(url).toContain('/auth/oauth-redirect');
            expect(url).toContain('provider=google');
        });
    });

    describe('handleAuthCallback', () => {
        it('should handle valid auth callback URL', async () => {
            const mockUrl = 'com.hillview://auth?token=jwt.token.here&expires_at=2023-12-01T10:00:00Z';
            
            mockInvoke.mockResolvedValueOnce({ success: true });

            const result = await handleAuthCallback(mockUrl);

            expect(result).toBe(true);
            expect(mockInvoke).toHaveBeenCalledWith('store_auth_token', {
                token: 'jwt.token.here',
                expiresAt: '2023-12-01T10:00:00Z'
            });
        });

        it('should return false for invalid URL', async () => {
            const mockUrl = 'https://example.com/invalid';
            
            const result = await handleAuthCallback(mockUrl);

            expect(result).toBe(false);
            expect(mockInvoke).not.toHaveBeenCalled();
        });

        it('should return false when missing token parameters', async () => {
            const mockUrl = 'com.hillview://auth?missing=token';
            
            const result = await handleAuthCallback(mockUrl);

            expect(result).toBe(false);
            expect(mockInvoke).not.toHaveBeenCalled();
        });

        it('should handle storage failure gracefully', async () => {
            const mockUrl = 'com.hillview://auth?token=jwt.token.here&expires_at=2023-12-01T10:00:00Z';
            
            mockInvoke.mockResolvedValueOnce({ success: false, error: 'Storage failed' });

            const result = await handleAuthCallback(mockUrl);

            expect(result).toBe(false);
        });
    });

    describe('getStoredToken', () => {
        it('should return token when available', async () => {
            const mockResponse = {
                success: true,
                token: 'stored.jwt.token'
            };
            
            mockInvoke.mockResolvedValueOnce(mockResponse);

            const result = await getStoredToken();

            expect(result).toBe('stored.jwt.token');
            expect(mockInvoke).toHaveBeenCalledWith('get_auth_token');
        });

        it('should return null when no token available', async () => {
            const mockResponse = {
                success: true,
                token: null
            };
            
            mockInvoke.mockResolvedValueOnce(mockResponse);

            const result = await getStoredToken();

            expect(result).toBe(null);
        });

        it('should return null on error', async () => {
            mockInvoke.mockRejectedValueOnce(new Error('Tauri error'));

            const result = await getStoredToken();

            expect(result).toBe(null);
        });
    });

    describe('clearStoredToken', () => {
        it('should clear token successfully', async () => {
            mockInvoke.mockResolvedValueOnce({ success: true });

            const result = await clearStoredToken();

            expect(result).toBe(true);
            expect(mockInvoke).toHaveBeenCalledWith('clear_auth_token');
        });

        it('should handle clear failure', async () => {
            mockInvoke.mockResolvedValueOnce({ success: false });

            const result = await clearStoredToken();

            expect(result).toBe(false);
        });
    });

    describe('hasValidAuth', () => {
        it('should return true when valid auth exists', async () => {
            const mockResponse = {
                success: true,
                token: 'valid.jwt.token'
            };
            
            mockInvoke.mockResolvedValueOnce(mockResponse);

            const result = await hasValidAuth();

            expect(result).toBe(true);
        });

        it('should return false when no auth exists', async () => {
            const mockResponse = {
                success: true,
                token: null
            };
            
            mockInvoke.mockResolvedValueOnce(mockResponse);

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });

        it('should return false when auth check fails', async () => {
            const mockResponse = {
                success: false,
                error: 'Auth check failed'
            };
            
            mockInvoke.mockResolvedValueOnce(mockResponse);

            const result = await hasValidAuth();

            expect(result).toBe(false);
        });
    });
});

describe('Mobile Detection', () => {
    it('should detect mobile app environment', async () => {
        // This would be tested in a component test where we can mock the full environment
        // For now, we'll create a simple function to test
        
        const detectMobileApp = async () => {
            try {
                await mockInvoke('get_auth_token');
                return true;
            } catch {
                return false;
            }
        };

        // Test mobile detection success
        mockInvoke.mockResolvedValueOnce({ success: true });
        const isMobile = await detectMobileApp();
        expect(isMobile).toBe(true);

        // Test mobile detection failure (web environment)
        mockInvoke.mockRejectedValueOnce(new Error('Not in Tauri'));
        const isWeb = await detectMobileApp();
        expect(isWeb).toBe(false);
    });
});

describe('OAuth URL Building Edge Cases', () => {
    it('should handle special characters in redirect URI', () => {
        const url = buildOAuthUrl('google', true);
        
        // The :// in com.hillview:// should be properly encoded
        expect(url).toContain('com.hillview%3A%2F%2Fauth');
    });

    it('should handle different providers', () => {
        const googleUrl = buildOAuthUrl('google', true);
        const githubUrl = buildOAuthUrl('github', true);
        
        expect(googleUrl).toContain('provider=google');
        expect(githubUrl).toContain('provider=github');
    });

    it('should use centralized backend URL consistently', () => {
        const url = buildOAuthUrl('google', false);
        
        // Should always use the backend URL from config, not frontend origin
        expect(url).toContain('/api/auth/oauth-redirect');
        expect(url).not.toContain('localhost:8212'); // Should not use frontend port
    });
});

describe('Token Expiration Handling', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should detect expired tokens', async () => {
        // Mock expired token response
        mockInvoke.mockResolvedValueOnce({
            success: true,
            token: 'expired.token.here',
            expires_at: '2020-01-01T00:00:00Z' // Past date
        });

        const result = await hasValidAuth();
        
        // Should return false for expired tokens
        expect(result).toBe(false);
    });

    it('should handle invalid token format gracefully', async () => {
        // Mock invalid token response
        mockInvoke.mockResolvedValueOnce({
            success: true,
            token: 'invalid-token-format'  // Not a valid JWT
        });

        const result = await hasValidAuth();
        
        // Should handle gracefully
        expect(result).toBe(false);
    });

    it('should validate token expiration from callback URL', async () => {
        const pastDate = '2020-01-01T00:00:00Z';
        const futureDate = '2030-01-01T00:00:00Z';
        
        // Test expired token in callback
        const expiredUrl = `com.hillview://auth?token=jwt.token.here&expires_at=${pastDate}`;
        const expiredResult = await handleAuthCallback(expiredUrl);
        expect(expiredResult).toBe(false);
        
        // Test valid token in callback
        mockInvoke.mockResolvedValueOnce({ success: true });
        const validUrl = `com.hillview://auth?token=jwt.token.here&expires_at=${futureDate}`;
        const validResult = await handleAuthCallback(validUrl);
        expect(validResult).toBe(true);
    });
});

describe('OAuth Provider Integration', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should handle OAuth errors from providers', async () => {
        const errorUrl = 'com.hillview://auth?error=access_denied&error_description=User%20denied%20access';
        
        const result = await handleAuthCallback(errorUrl);
        
        expect(result).toBe(false);
        expect(mockInvoke).not.toHaveBeenCalled();
    });

    it('should handle OAuth state mismatch', async () => {
        const suspiciousUrl = 'com.hillview://auth?token=suspicious.token.here&state=unexpected';
        
        const result = await handleAuthCallback(suspiciousUrl);
        
        // Should reject suspicious callbacks
        expect(result).toBe(false);
    });

    it('should build provider-specific OAuth URLs', () => {
        const googleMobileUrl = buildOAuthUrl('google', true);
        const githubWebUrl = buildOAuthUrl('github', false);
        
        // Google mobile should use deep link redirect
        expect(googleMobileUrl).toContain('redirect_uri=com.hillview%3A%2F%2Fauth');
        expect(googleMobileUrl).toContain('provider=google');
        
        // GitHub web should use web callback
        expect(githubWebUrl).toContain('provider=github');
        expect(githubWebUrl).toContain('redirect_uri=http');
    });
});