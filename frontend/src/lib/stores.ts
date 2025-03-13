import { writable } from 'svelte/store';
import { localStorageSharedStore } from './svelte-shared-store';

// Shared stores that can be imported by both auth and data modules
export const userPhotos = writable([]);

// Store for auto-upload folder settings
export const autoUploadSettings = localStorageSharedStore('autoUploadSettings', {
    enabled: false,
    folderPath: '',
    lastScanTime: null,
    uploadInterval: 30 // minutes
});

// Store for device type detection
export const deviceInfo = writable({
    isMobile: false,
    isIOS: false,
    isAndroid: false
});
