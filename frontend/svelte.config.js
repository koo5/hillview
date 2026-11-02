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

		// Cross-app shared modules (the zoom view's tile source, label layout/paint,
		// annotation targets, viewer init; the terrain overlay's labels) live in the
		// hillview_common submodule, which the recon workbench includes too. The
		// docker build COPYies it to /hillview_common (see Dockerfile; build context
		// is the repo root for that reason).
		alias: {
			$zoomview: '../hillview_common/zoomview',
			$terrain: '../hillview_common/terrain',
			// the 3D world (WorldScene and its layers), shared with the workbench's atlas viewer
			$world: '../hillview_common/world'
		},
		// hillview_common/world imports three (for types), copc and laz-perf from outside this tree:
		// resolve them to this app's copies, as vite's resolve.dedupe does at run time
		typescript: {
			config: (c) => {
				c.compilerOptions.paths.three = ['../node_modules/@types/three'];
				c.compilerOptions.paths['three/addons/*'] = ['../node_modules/@types/three/examples/jsm/*'];
				c.compilerOptions.paths.copc = ['../node_modules/copc'];
				c.compilerOptions.paths['laz-perf'] = ['../node_modules/laz-perf'];
			}
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
