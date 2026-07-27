import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type Plugin } from 'vite';

// Shared zoomview modules live in repo-root shared/ (consumed by the main
// frontend too — see docs/enrichment-workbench.md). The docker build COPYies
// that dir to the same relative spot (/shared/zoomview from /app).
const zoomview = new URL('../../shared/zoomview', import.meta.url).pathname;
const terrain = new URL('../../shared/terrain', import.meta.url).pathname;

// vite's watcher does not cover out-of-root modules (cf. the same plugin in
// frontend/vite.config.ts): without this, shared/* edits serve stale
// transforms until a dev-server restart.
const watchShared: Plugin = {
	name: 'watch-repo-shared',
	configureServer(server) {
		server.watcher.add([zoomview, terrain]);
	}
};

export default defineConfig({
	resolve: {
		alias: { $zoomview: zoomview, $terrain: terrain }
	},
	server: {
		host: true,
		port: 8071,
		// caddy fronts us on :8765 (and via the ygg address) — accept any Host
		allowedHosts: true,
		// same-origin /api on the direct dev server too
		proxy: { '/api': 'http://localhost:8070' },
		fs: { allow: ['.', zoomview, terrain] }
	},
	plugins: [
		watchShared,
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter()
		})
	]
});
