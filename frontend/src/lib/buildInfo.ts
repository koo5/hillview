// Build-time constants (declared in app.d.ts)
export const BUILD_TIME = __BUILD_TIME__;
export const BUILD_VERSION = __BUILD_VERSION__;
export const BUILD_GIT_COMMIT = __BUILD_GIT_COMMIT__;
export const DEBUG_MODE = __DEBUG_MODE__;

export function formatBuildTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toString();
}
