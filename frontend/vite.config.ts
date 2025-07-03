import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import Terminal from "vite-plugin-terminal";

export default defineConfig({
	plugins: [sveltekit(), Terminal({
		console: 'terminal',
		output: ['terminal', 'console']
	})],
	server: {
		host: true
	},
	define: {
		__BUILD_TIME__: JSON.stringify(new Date().toISOString()),
		__BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '0.0.1'),
		__DEBUG_MODE__: JSON.stringify(process.env.NODE_ENV !== 'production')
	}
});
