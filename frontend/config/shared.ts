/**
 * Shared configuration for both Vite and Vitest
 */

export const sharedDefines = {
  __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  __BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '0.0.1'),
  __DEBUG_MODE__: JSON.stringify(process.env.NODE_ENV !== 'production'),
  __WORKER_VERSION__: JSON.stringify(Date.now().toString())
};