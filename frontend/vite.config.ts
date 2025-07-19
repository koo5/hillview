import { sentrySvelteKit } from "@sentry/sveltekit";
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sentrySvelteKit({
        sourceMapsUploadOptions: {
            org: "ook-sy",
            project: "hillview"
        }
    }), sveltekit()],
	server: {
		host: true,
		hmr: {
			protocol: 'ws',
			host: process.env.TAURI_DEV_HOST || 'localhost',
			port: 8212
		}
	},
	define: {
		__BUILD_TIME__: JSON.stringify(new Date().toISOString()),
		__BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '0.0.1'),
		__DEBUG_MODE__: JSON.stringify(process.env.NODE_ENV !== 'production'),
		__WORKER_VERSION__: JSON.stringify(Date.now().toString())
	}
});