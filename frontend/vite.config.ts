import { sentrySvelteKit } from "@sentry/sveltekit";
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type Plugin } from 'vite';
import { sharedDefines } from './config/shared';

// Repo-root shared/ ($terrain/$zoomview aliases) sits outside the vite root,
// and vite's watcher does NOT cover out-of-root modules: edits there kept
// serving stale transforms until a dev-server restart while in-root edits
// hot-reloaded — a confusing half-updated state. Watching the dir explicitly
// makes the normal invalidation path fire for it.
const watchShared: Plugin = {
	name: 'watch-repo-shared',
	configureServer(server) {
		server.watcher.add(new URL('../shared', import.meta.url).pathname);
	}
};

export default defineConfig({
	plugins: [sentrySvelteKit(), sveltekit(), watchShared],
	server: {
		allowedHosts: ["dev.hillview.cz","jj.hillview.cz","hillview.dev4.local"],
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
