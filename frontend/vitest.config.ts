import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import path from 'path';
import { sharedDefines } from './config/shared';

export default defineConfig({
  plugins: [sveltekit()],
  define: sharedDefines,
  // hillview_common sits outside the project root — allow vitest's vite server
  // to serve it (scoped to ../hillview_common, matching vite.config.ts)
  server: { fs: { allow: ['.', '../hillview_common'] } },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/tests/setup.ts'],
    include: [
      'src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}',
      // the shared modules this app uses live in the hillview_common submodule; their tests
      // run here too, against this app's dependencies
      '../hillview_common/zoomview/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}',
      '../hillview_common/terrain/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/tests/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/.svelte-kit/**',
        'build/',
        'dist/',
      ],
    },
  },
  resolve: {
    alias: {
      $lib: path.resolve('./src/lib'),
      $zoomview: path.resolve('../hillview_common/zoomview'),
      $terrain: path.resolve('../hillview_common/terrain'),
      $app: path.resolve('./.svelte-kit/runtime/app'),
      'tauri-plugin-hillview-api': path.resolve('./src/tests/mocks/tauri-plugin-hillview-api.ts'),
    },
    conditions: ['browser'],
  },
});