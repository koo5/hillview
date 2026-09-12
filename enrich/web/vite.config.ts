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
// Build-time only, and read through globalThis because this project has no @types/node
// (a bare `process` does not type-check). Empty unless a build sets it.
//
// Validated here rather than trusted: a base path that is missing its leading slash, or
// carrying a trailing one, does not fail loudly — it produces a bundle whose every link
// and asset URL is subtly wrong, which you find out from a blank page in production.
function basePath(): '' | `/${string}` {
	const raw = (globalThis as { process?: { env?: Record<string, string | undefined> } })
		.process?.env?.BASE_PATH;
	if (!raw) return '';
	const v = raw.replace(/\/+$/, '');
	if (!v.startsWith('/') || v === '/') {
		throw new Error(
			`BASE_PATH must start with "/" and not be "/" alone (got ${JSON.stringify(raw)})`
		);
	}
	return v as `/${string}`;
}

const BASE_PATH = basePath();

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
			// Serve the whole app under a path prefix when BASE_PATH is set at BUILD time
			// (empty everywhere else, so dev and the tests are untouched). A prefix, not a
			// secret subdomain: hostnames land in Certificate Transparency logs minutes
			// after Caddy issues the cert, and paths never appear in a certificate.
			paths: { base: BASE_PATH },
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter()
		})
	]
});
