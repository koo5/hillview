<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { auth } from '$lib/authStore';
    import { showTokenRefreshIssue, removeAlertsBySource, addAlert } from '$lib/alertSystem.svelte';
    import { createTokenManager } from '$lib/tokenManagerFactory';

    let refreshStatusAlert: string | null = null;
    let retryTimeoutId: ReturnType<typeof setTimeout> | null = null;

    onMount(() => {
        // Watch for auth store changes
        const unsubscribe = auth.subscribe(authState => {
            handleRefreshStatusChange(authState.refresh_status, authState.refresh_attempt);
        });

        return () => {
            unsubscribe();
            if (retryTimeoutId) {
                clearTimeout(retryTimeoutId);
            }
        };
    });

    onDestroy(() => {
        if (retryTimeoutId) {
            clearTimeout(retryTimeoutId);
        }
    });

    function handleRefreshStatusChange(status: string, attempt?: number) {


        // Clear any existing refresh status alerts
        removeAlertsBySource('token_refresh_status');

        switch (status) {
            case 'refreshing':
                // Clear any existing timeout first
                if (retryTimeoutId) {
                    clearTimeout(retryTimeoutId);
                    retryTimeoutId = null;
                }
                // Only show alert after some seconds to avoid flashing for fast refreshes
                retryTimeoutId = setTimeout(() => {
                    refreshStatusAlert = addAlert(
                        'Refreshing authentication...',
                        'info',
                        {
                            priority: 6,
                            duration: 0, // Persistent until resolved
                            source: 'token_refresh_status',
                            dismissible: false // Can't dismiss active refresh
                        }
                    );
                    retryTimeoutId = null; // Clear the timeout ID after it fires
                }, 3000);
                break;

            case 'retrying':
                if (retryTimeoutId) {
                    clearTimeout(retryTimeoutId);
                    retryTimeoutId = null;
                }

                refreshStatusAlert = addAlert(
                    `Connection issues - retrying authentication (attempt ${attempt || 1})...`,
                    'warning',
                    {
                        priority: 7,
                        duration: 0, // Persistent until resolved
                        source: 'token_refresh_status',
                        dismissible: false // Can't dismiss active retry
                    }
                );
                break;

            case 'failed':
                if (retryTimeoutId) {
                    clearTimeout(retryTimeoutId);
                    retryTimeoutId = null;
                }

                refreshStatusAlert = showTokenRefreshIssue(
                    `Authentication failed after ${attempt || 1} attempts. Check your connection.`,
                    handleManualRetry
                );
                break;

            case 'idle':
            default:
                if (retryTimeoutId) {
                    clearTimeout(retryTimeoutId);
                    retryTimeoutId = null;
                }
                refreshStatusAlert = null;
                break;
        }
    }

    async function handleManualRetry() {
        try {
            const tokenManager = createTokenManager();
            const success = await tokenManager.refreshToken();

            if (success) {
                // Success will be handled by auth store update
                removeAlertsBySource('token_refresh');
                addAlert(
                    'Authentication restored',
                    'success',
                    {
                        priority: 5,
                        duration: 3000,
                        source: 'token_refresh'
                    }
                );
            }
        } catch (error) {
            console.error('🢄Manual token refresh failed:', error);
            // The auth store will update with failed status
        }
    }
</script>

<!-- This component has no visible output - it just watches and manages alerts -->
