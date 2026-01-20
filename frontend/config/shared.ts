import { execSync } from 'child_process';

/**
 * Shared configuration for both Vite and Vitest
 */

function getGitCommit(): string {
  try {
    return execSync('git rev-parse HEAD', { encoding: 'utf-8' }).trim();
  } catch {
    return 'unknown';
  }
}

export const sharedDefines = {
  __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  __BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '???'),
  __BUILD_GIT_COMMIT__: JSON.stringify(getGitCommit()),
  __DEBUG_MODE__: JSON.stringify(process.env.NODE_ENV !== 'production'),
  __WORKER_VERSION__: JSON.stringify(Date.now().toString())
};
