import { execSync } from 'child_process';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

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

function getTauriVersion(): string {
  try {
    const __dirname = dirname(fileURLToPath(import.meta.url));
    const tauriConfig = JSON.parse(
      readFileSync(join(__dirname, '../src-tauri/tauri.conf.json'), 'utf-8')
    );
    return tauriConfig.version || 'unknown';
  } catch {
    return 'unknown';
  }
}

export const sharedDefines = {
  __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  __BUILD_VERSION__: JSON.stringify(process.env.npm_package_version || '???'),
  __BUILD_GIT_COMMIT__: JSON.stringify(getGitCommit()),
  __DEBUG_MODE__: JSON.stringify(process.env.NODE_ENV !== 'production'),
  __WORKER_VERSION__: JSON.stringify(Date.now().toString()),
  __APP_VERSION__: JSON.stringify(getTauriVersion())
};
