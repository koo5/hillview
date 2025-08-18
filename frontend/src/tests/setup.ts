import { vi, beforeEach, afterEach } from 'vitest';

// Mock Tauri APIs
vi.mock('@tauri-apps/api/core', () => ({
    invoke: vi.fn()
}));

vi.mock('@tauri-apps/plugin-deep-link', () => ({
    onOpenUrl: vi.fn()
}));

import { backendUrl } from '../lib/config';

// Mock environment variables
vi.mock('$env/static/public', () => ({
    PUBLIC_API_URL: backendUrl
}));

// Mock SvelteKit stores
vi.mock('$app/stores', () => ({
    page: {
        subscribe: vi.fn(),
        url: {
            pathname: '/',
            searchParams: new URLSearchParams()
        }
    }
}));

// Global test utilities
global.fetch = vi.fn();

// Mock window.location
Object.defineProperty(window, 'location', {
    value: {
        origin: 'http://localhost:8212',
        href: 'http://localhost:8212/',
        pathname: '/',
        search: '',
        hash: ''
    },
    writable: true
});

// Mock console methods in tests to reduce noise
const originalConsole = { ...console };
beforeEach(() => {
    console.log = vi.fn();
    console.error = vi.fn();
    console.warn = vi.fn();
    console.info = vi.fn();
});

afterEach(() => {
    Object.assign(console, originalConsole);
});