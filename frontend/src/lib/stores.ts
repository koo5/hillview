import { writable } from 'svelte/store';

// Shared stores that can be imported by both auth and data modules
export const userPhotos = writable([]);
