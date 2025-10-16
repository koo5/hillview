import type { TokenManager } from './tokenManager';
import { AndroidTokenManager } from './androidTokenManager';
import { WebTokenManager } from './webTokenManager';
import { TAURI } from './tauri';

/**
 * Token Manager Factory
 *
 * Creates the appropriate token manager based on the current platform.
 * Provides a singleton instance to prevent multiple managers.
 */

let tokenManagerInstance: TokenManager | null = null;

/**
 * Detect if we're running on Android via Tauri
 */
function isAndroidTauri(): boolean {
    return TAURI && typeof window !== 'undefined' &&
           window.navigator.userAgent.includes('Android');
}

/**
 * Create or get the singleton token manager instance
 */
export function createTokenManager(): TokenManager {
    if (tokenManagerInstance) {
        return tokenManagerInstance;
    }

    if (isAndroidTauri()) {
        //console.log('🔐[FACTORY] Creating AndroidTokenManager');
        tokenManagerInstance = new AndroidTokenManager();
    } else {
        //console.log('🔐[FACTORY] Creating WebTokenManager');
        tokenManagerInstance = new WebTokenManager();
    }

    return tokenManagerInstance;
}

/**
 * Reset the token manager instance (for testing)
 */
export function resetTokenManager(): void {
    tokenManagerInstance = null;
}

/**
 * Get the current token manager type (for debugging)
 */
export function getTokenManagerType(): string {
    if (!tokenManagerInstance) {
        return 'none';
    }
    return tokenManagerInstance instanceof AndroidTokenManager ? 'android' : 'web';
}
