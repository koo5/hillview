// Build information
export const BUILD_TIME = __BUILD_TIME__;
export const BUILD_VERSION = __BUILD_VERSION__;
export const DEBUG_MODE = __DEBUG_MODE__;

export function getBuildInfo() {
    return {
        build_time: BUILD_TIME,
        build_version: BUILD_VERSION,
        debug_mode: DEBUG_MODE,
        formatted_time: new Date(BUILD_TIME).toLocaleString(undefined, {hour12: false})
    };
}