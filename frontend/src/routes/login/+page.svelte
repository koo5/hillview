<script lang="ts">
    import { onMount } from 'svelte';
    import { User, Lock, Mail, Github } from 'lucide-svelte';
    import { myGoto } from '$lib/navigation.svelte';
    import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
    import { login, register, oauthLogin, auth } from '$lib/auth.svelte';
    import { invoke } from '@tauri-apps/api/core';
    import { buildOAuthUrl } from '$lib/authCallback';
    import { getCurrentToken } from '$lib/auth.svelte';
    import { goBack, clearNavigationHistory, canNavigateBack } from '$lib/navigation.svelte';
    import { page } from '$app/stores';
    import { browser } from '$app/environment';
    import OAuthPolling from '../../components/OAuthPolling.svelte';
    import { TAURI } from '$lib/tauri';
    import { backendUrl } from '$lib/config';
    import { openUrl } from '@tauri-apps/plugin-opener';

    let username = '';
    let password = '';
    let email = '';
    let isLogin = true;
    let errorMessage = '';
    let successMessage = '';
    let isLoading = false;
    let usernameGenerated = false;

    // OAuth polling state - persistent across app reinitialization
    let isPolling = false;
    let pollingSessionId = '';
    let pollingProgress = 0;
    let pollingMessage = '';

    // Key for storing OAuth polling state
    const OAUTH_POLLING_KEY = 'hillview_oauth_polling_state';

    // Save OAuth polling state to localStorage
    function saveOAuthPollingState() {
        if (browser && isPolling && pollingSessionId) {
            const state = {
                isPolling,
                pollingSessionId,
                pollingProgress,
                pollingMessage,
                timestamp: Date.now()
            };
            localStorage.setItem(OAUTH_POLLING_KEY, JSON.stringify(state));
            console.log('🔐 Saved OAuth polling state:', pollingSessionId);
        }
    }

    // Restore OAuth polling state from localStorage
    function restoreOAuthPollingState() {
        if (!browser) return false;
        
        try {
            const storedState = localStorage.getItem(OAUTH_POLLING_KEY);
            if (storedState) {
                const state = JSON.parse(storedState);
                // Only restore if session is recent (within 10 minutes)
                if (state.timestamp && (Date.now() - state.timestamp) < 600000) {
                    isPolling = state.isPolling;
                    pollingSessionId = state.pollingSessionId;
                    pollingProgress = state.pollingProgress;
                    pollingMessage = state.pollingMessage || 'Continuing OAuth login...';
                    console.log('🔐 Restored OAuth polling state:', pollingSessionId);
                    return true;
                }
            }
        } catch (error) {
            console.warn('🔐 Failed to restore OAuth polling state:', error);
        }
        return false;
    }

    // Clear OAuth polling state from localStorage
    function clearOAuthPollingState() {
        if (browser) {
            localStorage.removeItem(OAUTH_POLLING_KEY);
            console.log('🔐 Cleared OAuth polling state');
        }
    }

    // Auto-fill dev credentials if in dev mode
    if (import.meta.env.VITE_DEV_MODE === 'true') {
        username = 'test';
        password = 'StrongTestPassword123!';
        //console.log('🢄[DEV] Auto-filled login credentials for development');
    }

    // OAuth configuration
    const oauthProviders: Record<string, {clientId: string; redirectUri: string; authUrl: string; scope: string}> = {
        google: {
            clientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
            redirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI || `${window.location.origin}/oauth/callback`,
            authUrl: 'https://accounts.google.com/o/oauth2/auth',
            scope: 'email profile'
        },
        github: {
            clientId: import.meta.env.VITE_GITHUB_CLIENT_ID || '',
            redirectUri: import.meta.env.VITE_GITHUB_REDIRECT_URI || `${window.location.origin}/oauth/callback`,
            authUrl: 'https://github.com/login/oauth/authorize',
            scope: 'user:email'
        }
    };

    onMount(async () => {
        console.log(`🢄🔐 Platform detected: ${TAURI ? 'Tauri app' : 'Web app'}`);

        if (TAURI) {
            // Check if user already has valid auth from previous session
            const token = await getCurrentToken();
            if (token) {
                console.log('🢄🔐 Found valid stored auth, redirecting to dashboard');
                clearOAuthPollingState(); // Clear any stale polling state
                myGoto('/');
                return;
            }

            // Try to restore OAuth polling state if app was reinitialized
            const restoredPolling = restoreOAuthPollingState();
            if (restoredPolling) {
                console.log('🔐 Resumed OAuth polling after app reinitialization');
                // Polling will restart automatically due to reactive statement
            }
        }

        // Check if user is already logged in (for web)
        auth.subscribe(value => {
            if (value.isAuthenticated && $page.url.pathname === '/login') {
                // Only redirect if we're actually on the login page
                console.log('🢄🔐 Already authenticated on login page, redirecting');
                clearOAuthPollingState(); // Clear polling state on successful auth
                if (canNavigateBack()) {
                    goBack('/');
                } else {
                    myGoto('/');
                }
            }
        });
    });

    async function handleSubmit() {
        isLoading = true;
        errorMessage = '';

        try {
            if (isLogin) {
                // Login
                console.log('🢄Attempting login for:', username);
                const success = await login(username, password);

                if (!success) {
                    throw new Error('Login failed. Please check your credentials and try again.');
                }

                // After successful login, go back to where user came from or home
                if (canNavigateBack()) {
                    goBack('/');
                } else {
                    myGoto('/');
                }
            } else {
                // Register
                console.log('🢄Registering with:', { email, username, password });
                const success = await register(email, username, password);

                if (!success) {
                    throw new Error('Registration failed. Please check the console for more details.');
                }

                // Switch to login form after successful registration
                isLogin = true;
                successMessage = 'Registration successful! Please log in.';
            }
        } catch (error) {
            console.error('🢄Form submission error:', error);
            errorMessage = error instanceof Error ? error.message : 'An error occurred';
        } finally {
            isLoading = false;
        }
    }

    async function handleOAuthLogin(provider: string) {
        if (!oauthProviders[provider]) {
            console.error('🢄Unsupported OAuth provider:', provider);
            return;
        }

        console.log(`🔐 Starting ${provider} OAuth flow (${TAURI ? 'tauri polling' : 'web'} mode)`);
        isLoading = true;
        errorMessage = '';

        if (TAURI) {
            // Tauri app: use polling mechanism
            // Step 1: Create OAuth session for polling
            console.log('🔐 Creating OAuth polling session...');
            const sessionResponse = await fetch(`${backendUrl}/auth/oauth-session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (!sessionResponse.ok) {
                throw new Error(`Failed to create OAuth session: ${sessionResponse.status}`);
            }

            const sessionData = await sessionResponse.json();
            const sessionId = sessionData.session_id;
            console.log('🔐 Created polling session:', sessionId);

            // Step 2: Build OAuth URL with session_id (no redirect_uri needed for polling)
            const authUrl = `${backendUrl}/auth/oauth-redirect?provider=${provider}&session_id=${sessionId}`;
            console.log('🢄🔐 Opening OAuth URL with polling:', authUrl);

            // Step 3: Open OAuth in system browser
            await openUrl(authUrl);

            // Step 4: Start polling for completion
            console.log('🔐 Starting OAuth polling...');
            isPolling = true;
            pollingSessionId = sessionId;
            pollingProgress = 0;
            pollingMessage = 'Complete login in the browser, then return here...';
            saveOAuthPollingState(); // Save state in case app gets reinitialized
            isLoading = false;
        } else {
            console.log('🢄 Web OAuth redirect');
            const authUrl = buildOAuthUrl(provider, TAURI);
            console.log('🢄🔐 Redirecting to:', authUrl);
            window.location.href = authUrl;
        }
    }

    function handleOAuthSuccess(event: CustomEvent) {
        console.log('🔐 OAuth polling completed successfully');
        pollingMessage = 'Login successful! Redirecting...';
        clearOAuthPollingState(); // Clear persisted state on success
        setTimeout(() => {
            isPolling = false;
            // Check if we have navigation history to go back to, otherwise go to home
            if (canNavigateBack()) {
                goBack('/');
            } else {
                myGoto('/');
            }
        }, 1000);
    }

    function handleOAuthError(event: CustomEvent) {
        console.error('🔐 OAuth polling failed:', event.detail.message);
        clearOAuthPollingState(); // Clear persisted state on error
        isPolling = false;
        errorMessage = event.detail.message || 'OAuth login failed. Please try again.';
        isLoading = false;
    }

    function handleOAuthCancel() {
        console.log('🔐 OAuth polling cancelled by user');
        clearOAuthPollingState(); // Clear persisted state on cancel
        isPolling = false;
        pollingMessage = '';
        errorMessage = '';
        isLoading = false;
    }

    function handleOAuthProgress(event: CustomEvent) {
        pollingProgress = event.detail.progress;
        pollingMessage = event.detail.message;
        saveOAuthPollingState(); // Update persisted state with progress
    }

    function generateUsername() {
        if (!isLogin && email && email.includes('@')) {
            // Extract username from email and add random numbers for uniqueness
            const baseUsername = email.split('@')[0].replace(/[^a-zA-Z0-9]/g, '');
            const randomSuffix = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
            username = baseUsername + randomSuffix;
            usernameGenerated = true;
        }
    }

    function toggleForm() {
        isLogin = !isLogin;
        errorMessage = '';
        successMessage = '';
        if (!isLogin && email) {
            generateUsername();
        }
    }
</script>

<div class="login-container page-scrollable">
    <StandardHeaderWithAlert 
        title={isLogin ? 'Login' : 'Register'} 
        showMenuButton={true}
        fallbackHref="/"
    />
    
    <div class="login-card">

        {#if errorMessage}
            <div class="error-message">{errorMessage}</div>
        {/if}

        {#if successMessage}
            <div class="success-message">{successMessage}</div>
        {/if}

        {#if isPolling}
            <OAuthPolling
                sessionId={pollingSessionId}
                isActive={isPolling}
                on:success={handleOAuthSuccess}
                on:error={handleOAuthError}
                on:cancel={handleOAuthCancel}
                on:progress={handleOAuthProgress}
            />
        {:else}
            <form on:submit|preventDefault={handleSubmit}>
            {#if !isLogin}
                <div class="form-group">
                    <label for="email">
                        <Mail size={20} />
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        bind:value={email}
                        on:input={generateUsername}
                        required
                        placeholder="Enter your email"
                    />
                </div>
            {/if}

            <div class="form-group">
                <label for="username">
                    <User size={20} />
                    Username {#if !isLogin && usernameGenerated}<span class="auto-generated">(auto-generated)</span>{/if}
                </label>
                <input
                    type="text"
                    id="username"
                    bind:value={username}
                    required
                    placeholder="Enter your username"
                    class:auto-generated={!isLogin && usernameGenerated}
                    on:focus={() => usernameGenerated = false}
                />
            </div>

            <div class="form-group">
                <label for="password">
                    <Lock size={20} />
                    Password
                </label>
                <input
                    type="password"
                    id="password"
                    bind:value={password}
                    required
                    placeholder="Enter your password"
                />
            </div>

            <div class="auth-buttons">
                <button type="submit" class="primary-button" disabled={isLoading}>
                    {isLoading ? 'Loading...' : isLogin ? 'Login' : 'Register'}
                </button>
                <button type="button" class="secondary-button" on:click={toggleForm}>
                    {isLogin ? 'Create Account' : 'Back to Login'}
                </button>
            </div>
            </form>
        {/if}

        {#if !isPolling}
            <div class="divider">
                <span>OR</span>
            </div>

            VITE_DEV_MODE: {import.meta.env.VITE_DEV_MODE}

            <div class="oauth-buttons">
            <button
                class="oauth-button google"
                on:click={() => handleOAuthLogin('google')}
                disabled={isLoading}
            >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Continue with Google
            </button>

            <button
                class="oauth-button github"
                on:click={() => handleOAuthLogin('github')}
                disabled={isLoading}
            >
                <Github size={20} />
                Continue with GitHub
            </button>
            </div>
        {/if}

    </div>
</div>

<style>
    .login-container {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        background-color: #f5f5f5;
        padding: 20px;
    }

    .login-card {
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        padding: 30px;
        width: 100%;
        max-width: 400px;
    }

    h1 {
        text-align: center;
        margin-bottom: 24px;
        color: #333;
    }

    .form-group {
        margin-bottom: 20px;
    }

    label {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        font-weight: 500;
        color: #555;
    }

    input {
        width: 100%;
        padding: 12px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
        transition: border-color 0.3s;
    }

    input:focus {
        border-color: #4a90e2;
        outline: none;
    }

    .auth-buttons {
        display: flex;
        gap: 12px;
        margin-bottom: 20px;
    }

    .primary-button {
        flex: 1;
        padding: 12px;
        background-color: #4a90e2;
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }

    .primary-button:hover {
        background-color: #3a7bc8;
    }

    .primary-button:disabled {
        background-color: #a0c0e8;
        cursor: not-allowed;
    }

    .secondary-button {
        flex: 1;
        padding: 12px;
        background-color: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }

    .secondary-button:hover {
        background-color: #e5e5e5;
    }

    .divider {
        display: flex;
        align-items: center;
        margin: 24px 0;
    }

    .divider::before,
    .divider::after {
        content: "";
        flex: 1;
        border-bottom: 1px solid #ddd;
    }

    .divider span {
        padding: 0 10px;
        color: #777;
        font-size: 14px;
    }

    .oauth-buttons {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .oauth-button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 12px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }

    .oauth-button.google {
        background-color: white;
        color: #333;
    }

    .oauth-button.github {
        background-color: #24292e;
        color: white;
    }

    .oauth-button:hover {
        opacity: 0.9;
    }


    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 10px;
        border-radius: 4px;
        margin-bottom: 20px;
        text-align: center;
    }

    .success-message {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 10px;
        border-radius: 4px;
        margin-bottom: 20px;
        text-align: center;
    }

    .auto-generated {
        font-size: 0.8em;
        color: #666;
        font-style: italic;
    }

    input.auto-generated {
        background-color: #f5f5f5;
    }

    .back-button-container {
        margin-bottom: 20px;
    }
</style>
