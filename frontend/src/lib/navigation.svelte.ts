import { writable, get } from 'svelte/store';
import { goto } from '$app/navigation';
import { browser } from '$app/environment';
import { page } from '$app/stores';
import { clearAlerts } from './alertSystem.svelte';

// Smart goto wrapper that avoids redundant navigation
export async function myGoto(path: string, options?: any): Promise<void> {
    if (!browser) return goto(path, options);

    const currentPage = get(page);
    const currentPath = currentPage.url.pathname;

    // Avoid navigation if already on the target page
    if (currentPath === path) {
        console.log(`🢄🧭 [NAV] myGoto: Already on "${path}", skipping navigation`);
        return;
    }

    console.log(`🢄🧭 [NAV] myGoto: Navigating from "${currentPath}" to "${path}"`);

    // Clear alerts when navigating to a new page
    clearAlerts();

    return goto(path, options);
}

// Simple navigation history store - just tracks our app's navigation
const navigationHistory = writable<string[]>([]);

// Current navigation state
export const navigationState = writable<{
    previousPath?: string;
    canGoBack: boolean;
}>({
    canGoBack: false
});

/**
 * Navigate to a path while tracking it in our history
 * This is the main navigation function to use instead of goto()
 */
export function navigateWithHistory(path: string, options?: { replaceState?: boolean; reason?: string }) {
    if (!browser) return myGoto(path, options);

    const currentPath = window.location.pathname;

    // Check if we're already there
    if (currentPath === path) {
        console.log(`🢄🧭 [NAV] Already on "${path}", skipping navigation${options?.reason ? ` (reason: ${options.reason})` : ''}`);
        return Promise.resolve();
    }

    // Log navigation
    console.log(`🢄🧭 [NAV] navigateWithHistory: Programmatic navigation from "${currentPath}" to "${path}"${options?.reason ? ` (reason: ${options.reason})` : ''}`);

    // Only add to history if we're not replacing state
    if (!options?.replaceState) {
        navigationHistory.update(history => {
            // Limit history to last 10 pages to prevent memory issues
            const newHistory = [...history, currentPath].slice(-10);
            console.log(`🢄🧭 [NAV] History updated (depth: ${newHistory.length})`);
            return newHistory;
        });

        // Update navigation state
        navigationState.update(() => ({
            previousPath: currentPath,
            canGoBack: true
        }));
    }

    return myGoto(path, options);
}

/**
 * Go back to the previous page in our tracked history
 * Falls back to a default path if no history available
 */
export function goBack(fallbackPath: string = '/') {
    if (!browser) return myGoto(fallbackPath);

    const history = get(navigationHistory);

    if (history.length > 0) {
        // Remove the last item from history and navigate to it
        navigationHistory.update(currentHistory => {
            const newHistory = [...currentHistory];
            const previousPath = newHistory.pop();

            if (previousPath) {
                console.log(`🢄🧭 [NAV] Going back to "${previousPath}" (remaining history: ${newHistory.length})`);

                // Update state
                navigationState.update(() => ({
                    previousPath: newHistory[newHistory.length - 1],
                    canGoBack: newHistory.length > 0
                }));

                // Navigate to previous path (myGoto will clear alerts)
                myGoto(previousPath);
            }

            return newHistory;
        });
    } else {
        // No history, go to fallback
        console.log(`🢄🧭 [NAV] No history, using fallback: "${fallbackPath}"`);
        console.trace('🧭 [NAV] goBack() called from:');
        myGoto(fallbackPath);
    }
}

/**
 * Clear all navigation history (useful after login/logout)
 */
export function clearNavigationHistory() {
    const history = get(navigationHistory);
    console.log(`🢄🧭 [NAV] Clearing navigation history (had ${history.length} entries)`);
    navigationHistory.set([]);
    navigationState.set({ canGoBack: false });
}

/**
 * Get the previous path for smart back navigation
 * Returns the fallback if no previous path exists
 */
export function getPreviousPath(fallbackPath: string = '/'): string {
    const history = get(navigationHistory);
    return history.length > 0 ? history[history.length - 1] : fallbackPath;
}

/**
 * Check if we can navigate back
 */
export function canNavigateBack(): boolean {
    return get(navigationHistory).length > 0;
}

// Export readonly version of history for debugging/inspection
export const readonlyNavigationHistory = { subscribe: navigationHistory.subscribe };
