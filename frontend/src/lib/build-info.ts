// Build information
export const BUILD_TIME = __BUILD_TIME__;
export const BUILD_VERSION = __BUILD_VERSION__;
export const DEBUG_MODE = __DEBUG_MODE__;

export function getBuildInfo() {
    return {
        buildTime: BUILD_TIME,
        buildVersion: BUILD_VERSION,
        debugMode: DEBUG_MODE,
        formattedTime: new Date(BUILD_TIME).toLocaleString(undefined, {hour12: false})
    };
}