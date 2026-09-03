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

// Hillview's own presence in the Panoramax federation. Once federated, the
// meta-catalog (api.panoramax.xyz) serves our own CC photos back through the
// panoramax source; the loader drops those to avoid duplicate markers next to
// the native hillview copies. Matching is by each item's rel=via link href
// (the origin instance URL), with our public photo-asset hosts as a fallback
// signal. Comma-separated env overrides cover dev deployments.
const parseUrlList = (raw: unknown, fallback: string[]): string[] =>
	typeof raw === 'string' && raw.trim()
		? raw.split(',').map((u) => u.trim()).filter(Boolean)
		: fallback;
export const ownPanoramaxInstanceUrls = parseUrlList(
	import.meta.env.VITE_OWN_PANORAMAX_INSTANCE_URLS,
	['https://panoramax.hillview.cz']
);
// Trailing slash enforced: these are matched with startsWith(), so a bare-host
// override like "https://pics.hillview.cz" would also match
// "https://pics.hillview.cz.evil.example/…" and hide a foreign photo.
export const ownPhotoAssetUrlPrefixes = parseUrlList(
	import.meta.env.VITE_OWN_PHOTO_ASSET_URL_PREFIXES,
	['https://pics.hillview.cz/', 'https://pics2.hillview.cz/', 'https://pics4.t3.storage.dev/']
).map((p) => (p.endsWith('/') ? p : p + '/'));

// Re-export constants for app use
export { MAX_DEBUG_MODES } from './constants';
