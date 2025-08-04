import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import path from 'path';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/tests/setup.ts'],
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
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
      $app: path.resolve('./.svelte-kit/runtime/app'),
      'tauri-plugin-hillview-api': path.resolve('./src/tests/mocks/tauri-plugin-hillview-api.ts'),
    },
  },
});