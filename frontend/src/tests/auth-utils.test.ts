import { describe, it, expect, beforeEach } from 'vitest';
import { buildOAuthUrl } from '$lib/authCallback';

describe('buildOAuthUrl', () => {
    beforeEach(() => {
        // Mock window.location.origin for web tests
        Object.defineProperty(window, 'location', {
            value: {
                origin: 'http://localhost:8212'
            },
            writable: true
        });
    });

    it('should build mobile OAuth URL with deep link redirect', () => {
        const url = buildOAuthUrl('google', true);

        expect(url).toContain('/auth/oauth-redirect');
        expect(url).toContain('provider=google');
        // Should use deep link scheme for mobile
        expect(url).toMatch(/redirect_uri=cz\.hillview(dev)?%3A%2F%2Fauth/);
    });

    it('should build web OAuth URL with web callback', () => {
        const url = buildOAuthUrl('github', false);

        expect(url).toContain('/auth/oauth-redirect');
        expect(url).toContain('provider=github');
        // Should use web callback URL
        expect(url).toContain('redirect_uri=http%3A%2F%2Flocalhost%3A8212%2Foauth%2Fcallback');
    });

    it('should handle different OAuth providers', () => {
        const googleUrl = buildOAuthUrl('google', true);
        const githubUrl = buildOAuthUrl('github', true);

        expect(googleUrl).toContain('provider=google');
        expect(githubUrl).toContain('provider=github');
    });

    it('should properly encode special characters in redirect URI', () => {
        const url = buildOAuthUrl('google', true);

        // The :// in cz.hillview:// should be properly encoded
        expect(url).toMatch(/cz\.hillview(dev)?%3A%2F%2Fauth/);
    });

    it('should use backend URL from config', () => {
        const url = buildOAuthUrl('google', false);

        // Should contain the API path
        expect(url).toContain('/api/auth/oauth-redirect');
    });
});
