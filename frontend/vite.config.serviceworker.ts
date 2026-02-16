import { defineConfig } from 'vite';
import { resolve } from 'path';

// Vite config specifically for building the service worker modules
export default defineConfig({
    resolve: {
        alias: {
            '$lib': resolve(__dirname, 'src/lib')
        }
    },
    build: {
        lib: {
            entry: resolve(__dirname, 'src/lib/browser/serviceWorkerBundle.ts'),
            name: 'ServiceWorkerBundle',
            formats: ['iife'],
            fileName: () => 'serviceWorkerBundle.js'
        },
        outDir: 'static',
        emptyOutDir: false,
        rollupOptions: {
            output: {
                format: 'iife',
                name: 'ServiceWorkerBundle',
                extend: true
            }
        },
        target: 'esnext',
        minify: false
    },
    define: {
        'process.env.NODE_ENV': '"production"'
    }
});