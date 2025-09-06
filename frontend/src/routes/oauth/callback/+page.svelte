<script lang="ts">
    import { onMount } from 'svelte';
    import { oauthLogin } from '$lib/auth.svelte';
    import Spinner from '../../../components/Spinner.svelte';
    import { clearNavigationHistory, myGoto } from '$lib/navigation.svelte';
    import { handleAuthCallback } from '$lib/authCallback';

    let status = 'Processing your login...';
    let error: string | null = null;

    onMount(async () => {
        try {
            // Check if this is a mobile browser within the Tauri app
            const isMobileApp = window.navigator.userAgent.includes('hillview') || !!(window as any).__TAURI_INTERNALS__;
            
            // Check if we have OAuth callback parameters
            const urlParams = new URLSearchParams(window.location.search);
            const code = urlParams.get('code');
            const state = urlParams.get('state');
            const errorParam = urlParams.get('error');
            
            // Check if we have a deep link token (fallback case)
            const token = urlParams.get('token');
            const expires_at = urlParams.get('expires_at');
            
            if (errorParam) {
                throw new Error(`OAuth error: ${errorParam}`);
            }
            
            // Handle deep link token case (when browser intercepted the deep link)
            if (token && expires_at && isMobileApp) {
                console.log('🢄🔐 Handling intercepted deep link token in browser');
                status = 'Processing authentication...';
                
                // Handle auth callback
                const deepLinkUrl = `cz.hillview://auth?token=${token}&expires_at=${expires_at}`;
                
                const success = await handleAuthCallback(deepLinkUrl);
                if (success) {
                    status = 'Login successful! Redirecting...';
                    setTimeout(() => {
                        myGoto('/');
                    }, 1000);
                    return;
                } else {
                    throw new Error('Failed to process authentication token');
                }
            }
            
            // Handle standard OAuth code exchange
            if (!code || !state) {
                // If we're in mobile app without proper parameters, show helpful message
                if (isMobileApp) {
                    status = 'Please try logging in again';
                    error = 'OAuth flow was interrupted. Please return to the app and try again.';
                    setTimeout(() => {
                        myGoto('/login');
                    }, 3000);
                    return;
                } else {
                    throw new Error('Invalid OAuth callback parameters');
                }
            }
            
            // Parse provider from state (format: "provider:redirect_uri")
            const provider = state.includes(':') ? state.split(':')[0] : state;
            
            // Exchange code for token
            const success = await oauthLogin(
                provider, 
                code, 
                `${window.location.origin}/oauth/callback`
            );
            
            if (!success) {
                throw new Error('OAuth authentication failed');
            }
            
            status = 'Login successful! Redirecting...';
            
            // OAuth flow disrupts navigation history, so clear it and go to home
            clearNavigationHistory();
            setTimeout(() => {
                myGoto('/');
            }, 1000);
            
        } catch (err) {
            console.error('🢄OAuth callback error:', err);
            error = err instanceof Error ? err.message : 'Authentication failed';
            status = 'Authentication failed';
            
            // Redirect to login page after a delay
            setTimeout(() => {
                myGoto('/login');
            }, 3000);
        }
    });
</script>

<div class="oauth-callback">
    <div class="callback-card">
        <h1>{status}</h1>
        
        {#if error}
            <div class="error-message">{error}</div>
            <p>Redirecting to login page...</p>
        {:else}
            <Spinner />
        {/if}
    </div>
</div>

<style>
    .oauth-callback {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        background-color: #f5f5f5;
        padding: 20px;
    }
    
    .callback-card {
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        padding: 30px;
        width: 100%;
        max-width: 400px;
        text-align: center;
    }
    
    h1 {
        margin-bottom: 24px;
        color: #333;
        font-size: 24px;
    }
    
    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 10px;
        border-radius: 4px;
        margin-bottom: 20px;
    }
    
    p {
        color: #666;
        margin-top: 20px;
    }
</style>
