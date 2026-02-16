#!/usr/bin/env node

// Build script to bundle service worker upload module
import esbuild from 'esbuild';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function build() {
    try {
        await esbuild.build({
            entryPoints: [path.join(__dirname, '../src/lib/browser/serviceWorkerUpload.ts')],
            bundle: true,
            format: 'iife',
            globalName: 'ServiceWorkerUpload',
            platform: 'browser',
            target: 'es2020',
            outfile: path.join(__dirname, '../static/serviceWorkerUpload.js'),
            minify: false,
            sourcemap: false,
            define: {
                'self': 'self'
            }
        });

        console.log('Service worker upload module built successfully');
    } catch (error) {
        console.error('Build failed:', error);
        process.exit(1);
    }
}

build();