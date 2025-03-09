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
	}
});
