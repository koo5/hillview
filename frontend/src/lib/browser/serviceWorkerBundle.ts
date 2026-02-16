// Bundle entry point for service worker
// This exports everything the service worker needs in a format it can use

import { swUploader } from './serviceWorkerUpload';

// Version will be injected at build time
declare const __SW_VERSION__: string;

// Make the version available globally
(self as any).SW_BUNDLE_VERSION = typeof __SW_VERSION__ !== 'undefined' ? __SW_VERSION__ : 'dev';

// Make the uploader available globally in the service worker context
(self as any).swUploader = swUploader;

// Log version on load
console.log(`[ServiceWorkerBundle] Version: ${(self as any).SW_BUNDLE_VERSION}`);

// Export for module systems if needed
export { swUploader };