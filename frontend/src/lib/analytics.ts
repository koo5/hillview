/**
 * Lightweight analytics wrapper around Umami.
 * Fails silently when Umami is not loaded (Tauri, ad-blocked, no website ID configured).
 */

declare global {
	interface Window {
		umami?: {
			track: (eventOrProps?: string | Record<string, unknown>, data?: Record<string, unknown>) => void;
		};
	}
}

export function track(event: string, data?: Record<string, string | number | boolean>) {
	window.umami?.track(event, data);
}
