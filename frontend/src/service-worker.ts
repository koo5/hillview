/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/// <reference types="@sveltejs/kit" />

import { swUploader } from '$lib/browser/serviceWorkerBundle';

declare const self: ServiceWorkerGlobalScope;

self.addEventListener('sync', (event) => {
    if (event.tag === 'photo-upload') {
        event.waitUntil(swUploader.uploadPendingPhotos());
    }
});
