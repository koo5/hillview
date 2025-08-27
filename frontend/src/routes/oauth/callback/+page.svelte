<script lang="ts">
    import { onMount } from 'svelte';
    import { oauthLogin } from '$lib/auth.svelte';
    import Spinner from '../../../components/Spinner.svelte';
    import { clearNavigationHistory, myGoto } from '$lib/navigation.svelte';

    let status = 'Processing your login...';
    let error: string | null = null;

    onMount(async () => {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            const code = urlParams.get('code');
            const state = urlParams.get('state'); // Provider name
            const errorParam = urlParams.get('error');
            
            if (errorParam) {
                throw new Error(`OAuth error: ${errorParam}`);
            }
            
            if (!code || !state) {
                throw new Error('Invalid OAuth callback parameters');
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
