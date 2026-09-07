// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			/**
			 * Read-only SSR ticket from the visitor's cookie, when authed rendering
			 * is switched on. Server loads forward it to the API as a bearer token so
			 * the page renders this visitor's view; absent means render anonymously.
			 * See hooks.server.ts and $lib/ssrTicketCookie.ts.
			 */
			ssrTicket?: string;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	// Build-time constants injected by Vite
	const __BUILD_TIME__: string;
	const __BUILD_VERSION__: string;
	const __BUILD_GIT_COMMIT__: string;
	const __DEBUG_MODE__: string;

	// AbsoluteOrientationSensor API types
	interface AbsoluteOrientationSensorOptions {
		frequency?: number;
		referenceFrame?: 'device' | 'screen';
	}

	class AbsoluteOrientationSensor extends EventTarget {
		constructor(options?: AbsoluteOrientationSensorOptions);
		readonly quaternion: Float64Array;
		start(): void;
		stop(): void;
		addEventListener(type: 'reading', listener: () => void): void;
		addEventListener(type: 'error', listener: (event: Event) => void): void;
		removeEventListener(type: 'reading', listener: () => void): void;
		removeEventListener(type: 'error', listener: (event: Event) => void): void;
	}

	interface Window {
		AbsoluteOrientationSensor: typeof AbsoluteOrientationSensor;
	}
}

export {};
