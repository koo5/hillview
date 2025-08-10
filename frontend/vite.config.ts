import { sentrySvelteKit } from "@sentry/sveltekit";
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { sharedDefines } from './config/shared';

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
	define: sharedDefines
});