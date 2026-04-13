/**
 * Lightweight analytics wrapper around Umami.
 * Fails silently when Umami is not loaded (Tauri, ad-blocked, no website ID configured).
 */

declare global {
	interface Window {
		umami?: {
			track: (eventOrFn?: string | ((props: Record<string, unknown>) => Record<string, unknown>), data?: Record<string, unknown>) => void;
			identify: (idOrData: string | Record<string, unknown>, data?: Record<string, unknown>) => void;
		};
	}
}

export function track(event: string, data?: Record<string, string | number | boolean>) {
	window.umami?.track((props) => ({...props, url: location.pathname, name: event, data}));
}

export function identify(userId: string, data?: Record<string, string | number | boolean>) {
	window.umami?.identify(userId, data);
}
