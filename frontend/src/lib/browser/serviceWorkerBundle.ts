// Bundle entry point for service worker
// This exports everything the service worker needs in a format it can use

import { swUploader } from './serviceWorkerUpload';

// Make the uploader available globally in the service worker context
(self as any).swUploader = swUploader;

// Export for module systems if needed
export { swUploader };