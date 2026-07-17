import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Shared zoomview modules live in repo-root shared/ (consumed by the main
// frontend too — see docs/enrichment-workbench.md). The docker build COPYies
// that dir to the same relative spot (/shared/zoomview from /app).
const zoomview = new URL('../../shared/zoomview', import.meta.url).pathname;

export default defineConfig({
	resolve: {
		alias: { $zoomview: zoomview }
	},
	server: {
		host: true,
		port: 8071,
		// caddy fronts us on :8765 (and via the ygg address) — accept any Host
		allowedHosts: true,
		// same-origin /api on the direct dev server too
		proxy: { '/api': 'http://localhost:8070' },
		fs: { allow: ['.', zoomview] }
	},
	plugins: [
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
