import adapterStatic from '@sveltejs/adapter-static';
import adapterNode from '@sveltejs/adapter-node';
import {vitePreprocess} from '@sveltejs/vite-plugin-svelte';

// Use Node adapter for Docker/server deployment, static for Tauri builds
const adapter = process.env.ADAPTER === 'node' ? adapterNode() : adapterStatic({
	pages: 'build',
	assets: 'build',
	fallback: 'index.html',
	precompress: false,
	strict: false
});

const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
		// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
		// See https://svelte.dev/docs/kit/adapters for more information about adapters.
		adapter,

		// Cross-app shared zoomview modules (tile source, label layout/paint,
		// annotation targets, viewer init) — consumed by the enrichment workbench
		// too (enrich/web). The docker build COPYies this dir to /shared/zoomview
		// (see Dockerfile; build context is the repo root for that reason).
		alias: {
			$zoomview: '../shared/zoomview'
		},

		/*experimental: {
			tracing: {
				server: true
			},

			instrumentation: {
				server: true
			}
		}*/
	}
};

export default config;
