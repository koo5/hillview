// Browser-compatible auto-upload settings using localStorage
import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';

export interface BrowserAutoUploadSettings {
    auto_upload_enabled: boolean;
    auto_upload_prompt_enabled: boolean;
}

const STORAGE_KEY = 'browser_auto_upload_settings';

// Default settings for browser
const defaultSettings: BrowserAutoUploadSettings = {
    auto_upload_enabled: false,
    auto_upload_prompt_enabled: true
};

// Create store
export const browserAutoUploadSettings = writable<BrowserAutoUploadSettings>(defaultSettings);

// Load settings from localStorage on initialization
if (browser) {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            const parsed = JSON.parse(stored);
            browserAutoUploadSettings.set({
                ...defaultSettings,
                ...parsed
            });
        }
    } catch (error) {
        console.error('Failed to load browser auto-upload settings:', error);
    }
}

// Save settings to localStorage when they change
browserAutoUploadSettings.subscribe((settings) => {
    if (browser) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
        } catch (error) {
            console.error('Failed to save browser auto-upload settings:', error);
        }
    }
});

// Helper functions
export function getBrowserAutoUploadSettings(): BrowserAutoUploadSettings {
    return get(browserAutoUploadSettings);
}

export function setBrowserAutoUploadSettings(settings: Partial<BrowserAutoUploadSettings>): void {
    browserAutoUploadSettings.update(current => ({
        ...current,
        ...settings
    }));
}