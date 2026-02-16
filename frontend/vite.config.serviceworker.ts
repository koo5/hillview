import { defineConfig } from 'vite';
import { resolve } from 'path';
import { createHash } from 'crypto';
import { readFileSync } from 'fs';

// Generate version based on source file content hash
function generateVersion() {
    const sourceFiles = [
        'src/lib/browser/serviceWorkerBundle.ts',
        'src/lib/browserPhotoStorage.ts',
        'src/lib/browser/sharedTokenRefresh.ts'
    ];

    let combinedContent = '';
    for (const file of sourceFiles) {
        try {
            combinedContent += readFileSync(resolve(__dirname, file), 'utf-8');
        } catch (e) {
            console.warn(`Could not read ${file} for version hash`);
        }
    }

    const hash = createHash('sha256').update(combinedContent).digest('hex').substring(0, 8);
    const buildTime = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
    return `${buildTime}-${hash}`;
}

const SW_VERSION = generateVersion();
console.log(`Building service worker bundle version: ${SW_VERSION}`);

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
        'process.env.NODE_ENV': '"production"',
        '__SW_VERSION__': JSON.stringify(SW_VERSION)
    }
});