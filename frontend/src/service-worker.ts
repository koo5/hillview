/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/// <reference types="@sveltejs/kit" />

import { handleSync } from '$lib/sw/backgroundSync';
import { handleFetch, handleMessage } from '$lib/sw/tileHandler';

declare const self: ServiceWorkerGlobalScope;

// Background Sync for photo uploads
self.addEventListener('sync', (event) => {
    handleSync(event);
});

// Tile fetch interception (error tiles on failure)
self.addEventListener('fetch', (event) => {
    handleFetch(event);
});

// Messages from main thread (tile provider updates)
self.addEventListener('message', (event) => {
    handleMessage(event);
});
