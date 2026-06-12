import { TAURI_MOBILE } from './tauri';
//console.log('🢄🔍🔍 TAURI_MOBILE:', TAURI_MOBILE);

export const backendUrl = (TAURI_MOBILE ? import.meta.env.VITE_BACKEND_ANDROID : import.meta.env.VITE_BACKEND) || 'http://localhost:8055/api';
export const FEATURE_USER_ACCOUNTS = import.meta.env.VITE_FEATURE_USER_ACCOUNTS === 'true' || import.meta.env.VITE_FEATURE_USER_ACCOUNTS === true;
export const liveshareBackendUrl = import.meta.env.VITE_LIVESHARE_BACKEND || 'http://localhost:8057/liveshare';

// Debounce window for per-photo detail fetches (ratings, flag status).
// Suppresses bursts of requests when the user rapidly swipes through the gallery.
const photoDetailFetchDebounceParsed = parseInt(import.meta.env.VITE_PHOTO_DETAIL_FETCH_DEBOUNCE_MS, 10);
export const PHOTO_DETAIL_FETCH_DEBOUNCE_MS = Number.isFinite(photoDetailFetchDebounceParsed) && photoDetailFetchDebounceParsed >= 0
	? photoDetailFetchDebounceParsed
	: 250;

// Re-export constants for app use
export { MAX_DEBUG_MODES } from './constants';
