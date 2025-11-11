<script lang="ts">
    import { onMount } from 'svelte';
    import { myGoto } from '$lib/navigation.svelte';
    import Spinner from '$lib/components/Spinner.svelte';
    import { handleAuthCallback } from '$lib/authCallback';

    let status = 'Completing authentication...';
    let error: string | null = null;

    onMount(async () => {
        try {
            // This page handles mobile OAuth fallback when deep links fail
            console.log('🢄🔐 Mobile OAuth fallback page loaded');

            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');
            const expires_at = urlParams.get('expires_at');
            const refresh_token = urlParams.get('refresh_token');

            if (!token || !expires_at) {
                throw new Error('Missing authentication parameters');
            }

            console.log('🢄🔐 Processing fallback authentication with token');
            status = 'Processing authentication...';

            // Handle auth callback

            // Construct the deep link URL and process it
            let deepLinkUrl = `cz.hillview://auth?token=${token}&expires_at=${expires_at}`;
            if (refresh_token) {
                deepLinkUrl += `&refresh_token=${refresh_token}`;
            }

            const success = await handleAuthCallback(deepLinkUrl);

            if (success) {
                status = 'Authentication successful!';
                console.log('🢄🔐 Fallback authentication completed successfully');

                // Give user feedback then redirect
                setTimeout(() => {
                    myGoto('/');
                }, 1500);
            } else {
                throw new Error('Failed to complete authentication');
            }

        } catch (err) {
            console.error('🢄🔐 Mobile OAuth fallback error:', err);
            error = err instanceof Error ? err.message : 'Authentication failed';
            status = 'Authentication failed';

            // Redirect to login page after showing error
            setTimeout(() => {
                myGoto('/login');
            }, 3000);
        }
    });
</script>

<div class="mobile-callback">
    <div class="callback-card">
        <h1>Hillview</h1>
        <h2>{status}</h2>

        {#if error}
            <div class="error-message">
                <strong>Error:</strong> {error}
            </div>
            <p>You will be redirected to the login page...</p>
        {:else}
            <Spinner />
            <p>Please wait while we complete your login...</p>
        {/if}

        <div class="help-text">
            <p><strong>Having trouble?</strong></p>
            <p>Close this browser tab and return to the Hillview app.</p>
        </div>
    </div>
</div>

<style>
    .mobile-callback {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    }

    .callback-card {
        background: white;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        padding: 40px;
        width: 100%;
        max-width: 400px;
        text-align: center;
    }

    h1 {
        color: #333;
        font-size: 24px;
        font-weight: 600;
        margin-bottom: 8px;
        margin-top: 0;
    }

    h2 {
        color: #666;
        font-size: 18px;
        font-weight: 400;
        margin-bottom: 24px;
        margin-top: 0;
    }

    .error-message {
        background-color: #fee;
        color: #c33;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 20px;
        border: 1px solid #fcc;
    }

    p {
        color: #666;
        margin-bottom: 16px;
        line-height: 1.4;
    }

    .help-text {
        margin-top: 24px;
        padding-top: 24px;
        border-top: 1px solid #eee;
    }

    .help-text p {
        font-size: 14px;
        color: #888;
        margin-bottom: 8px;
    }

    .help-text p:first-child {
        font-weight: 600;
        color: #666;
    }
</style>
