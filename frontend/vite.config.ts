import { sentrySvelteKit } from "@sentry/sveltekit";
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { sharedDefines } from './config/shared';

export default defineConfig({
	plugins: [sentrySvelteKit(), sveltekit()],
	server: {
		allowedHosts: ["dev.hillview.cz","jj.hillview.cz"],
		host: true,
		// $zoomview resolves outside the project root; allow ONLY ../shared —
		// never '..' (the repo root holds secrets/, and this dev server binds
		// publicly). Listing any allow replaces the default, so '.' stays too.
		fs: { allow: ['.', '../shared'] },
		port: parseInt(process.env.VITE_DEV_PORT || '8212'),
		hmr: {
			protocol: 'ws',
			host: process.env.TAURI_DEV_HOST || 'localhost',
			port: parseInt(process.env.VITE_DEV_PORT || '8212')
		}
	},
	define: sharedDefines
	/*test: {
			environment: 'happy-dom',
			globals: true,
			setupFiles: ['src/tests/setup.ts']
	}
	*/
});
