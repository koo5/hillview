import { writable, get } from 'svelte/store';
import { goto } from '$app/navigation';
import { browser } from '$app/environment';

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
export function navigateWithHistory(path: string, options?: { replaceState?: boolean }) {
    if (!browser) return goto(path, options);
    
    const currentPath = window.location.pathname;
    
    // Only add to history if we're not replacing state and it's a different page
    if (!options?.replaceState && currentPath !== path) {
        navigationHistory.update(history => {
            // Limit history to last 10 pages to prevent memory issues
            const newHistory = [...history, currentPath].slice(-10);
            return newHistory;
        });
        
        // Update navigation state
        navigationState.update(() => ({
            previousPath: currentPath,
            canGoBack: true
        }));
    }
    
    return goto(path, options);
}

/**
 * Go back to the previous page in our tracked history
 * Falls back to a default path if no history available
 */
export function goBack(fallbackPath: string = '/') {
    if (!browser) return goto(fallbackPath);
    
    const history = get(navigationHistory);
    
    if (history.length > 0) {
        // Remove the last item from history and navigate to it
        navigationHistory.update(currentHistory => {
            const newHistory = [...currentHistory];
            const previousPath = newHistory.pop();
            
            if (previousPath) {
                // Update state
                navigationState.update(() => ({
                    previousPath: newHistory[newHistory.length - 1],
                    canGoBack: newHistory.length > 0
                }));
                
                // Navigate to previous path
                goto(previousPath);
            }
            
            return newHistory;
        });
    } else {
        // No history, go to fallback
        goto(fallbackPath);
    }
}

/**
 * Clear all navigation history (useful after login/logout)
 */
export function clearNavigationHistory() {
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