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
}

// openseadragon ships no type declarations (the main frontend imports it
// untyped too) — treat the module as any
declare module 'openseadragon';

export {};
