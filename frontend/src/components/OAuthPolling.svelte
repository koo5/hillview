<script lang="ts">
    import { createEventDispatcher } from 'svelte';
    import { backendUrl } from '$lib/config';
    import { completeAuthentication } from '$lib/auth.svelte';

    export let sessionId: string;
    export let isActive: boolean = true;

    const dispatch = createEventDispatcher<{
        cancel: void;
        success: { tokens: any };
        error: { message: string };
        progress: { progress: number; message: string };
    }>();

    // Internal state - component manages its own progress and message
    let progress: number = 0;
    let message: string = 'Complete login in the browser, then return here...';
    let cancelled = false;

    async function pollForCompletion() {
        const maxAttempts = 60; // 5 minutes at 5-second intervals
        let attempts = 0;

        const poll = async () => {
            // Check for cancellation
            if (cancelled || !isActive) {
                console.log('🢄🔐 Polling cancelled');
                return;
            }

            attempts++;
            progress = Math.min((attempts / maxAttempts) * 100, 95); // Cap at 95% until complete
            
            console.log(`🢄🔐 Polling attempt ${attempts}/${maxAttempts} for session ${sessionId}`);
            
            // Dispatch progress update
            dispatch('progress', { progress, message });

            try {
                const response = await fetch(`${backendUrl}/auth/oauth-status/${sessionId}`);
                
                if (response.ok) {
                    // OAuth completed successfully
                    const tokenData = await response.json();
                    console.log('🢄🔐 OAuth tokens received via polling');
                    progress = 100;
                    message = 'Processing authentication...';
                    dispatch('progress', { progress, message });
                    
                    // Complete authentication using existing logic
                    const authSuccess = await completeAuthentication({
                        access_token: tokenData.access_token,
                        refresh_token: tokenData.refresh_token,
                        expires_at: tokenData.expires_at,
                        token_type: tokenData.token_type,
                        refresh_token_expires_at: tokenData.refresh_token_expires_at
                    }, 'oauth');

                    if (authSuccess) {
                        dispatch('success', { tokens: tokenData });
                    } else {
                        dispatch('error', { message: 'Failed to complete authentication' });
                    }
                    return;
                } else if (response.status === 404) {
                    // Session not found or expired
                    if (attempts >= maxAttempts) {
                        console.error('🢄🔐 OAuth polling timed out');
                        message = 'Login timed out. Please try again.';
                        dispatch('error', { message: 'OAuth polling timed out' });
                        return;
                    }
                    // Continue polling - update message based on time elapsed
                    const elapsed = attempts * 5; // seconds
                    if (elapsed > 120) {
                        message = 'Still waiting... Please check the browser tab.';
                    } else if (elapsed > 60) {
                        message = 'Taking longer than expected... Please complete login in browser.';
                    } else {
                        message = 'Complete login in the browser, then return here...';
                    }
                } else {
                    // Other error
                    console.error('🢄🔐 OAuth polling error:', response.status);
                    message = `Polling error (${response.status}). Please try again.`;
                    dispatch('error', { message: `Polling error: ${response.status}` });
                    return;
                }
            } catch (error) {
                console.error('🢄🔐 OAuth polling request failed:', error);
                if (attempts >= maxAttempts) {
                    message = 'Connection error. Please try again.';
                    dispatch('error', { message: 'Connection error during polling' });
                    return;
                }
                message = 'Connection issue, retrying...';
            }

            // Continue polling after delay
            setTimeout(poll, 5000); // Poll every 5 seconds
        };

        poll();
    }

    function handleCancel() {
        cancelled = true;
        dispatch('cancel');
    }

    // Start polling when component mounts
    let pollingStarted = false;
    $: if (sessionId && isActive && !pollingStarted) {
        pollingStarted = true;
        pollForCompletion();
    }
</script>

<div class="polling-status">
    <div class="polling-header">
        <h3>Completing OAuth Login</h3>
    </div>
    
    <div class="progress-bar">
        <div class="progress-fill" style="width: {progress}%"></div>
    </div>
    
    <div class="polling-message">{message}</div>
    
    <div class="polling-actions">
        <button type="button" class="cancel-button" on:click={handleCancel}>
            Cancel Login
        </button>
    </div>
</div>

<style>
    .polling-status {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 24px;
        margin-bottom: 20px;
        text-align: center;
    }

    .polling-header h3 {
        margin: 0 0 16px 0;
        color: #333;
        font-size: 18px;
    }

    .progress-bar {
        width: 100%;
        height: 8px;
        background: #e9ecef;
        border-radius: 4px;
        margin-bottom: 16px;
        overflow: hidden;
    }

    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #4a90e2, #357abd);
        transition: width 0.3s ease;
        border-radius: 4px;
    }

    .polling-message {
        color: #666;
        font-size: 14px;
        margin-bottom: 20px;
        line-height: 1.4;
    }

    .polling-actions {
        display: flex;
        justify-content: center;
    }

    .cancel-button {
        background: #dc3545;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }

    .cancel-button:hover {
        background: #c82333;
    }
</style>