// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	// Build-time constants injected by Vite
	const __BUILD_TIME__: string;
	const __BUILD_VERSION__: string;
	const __DEBUG_MODE__: string;
	const __WORKER_VERSION__: string;

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
