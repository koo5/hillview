<script>
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { User, Lock, Mail, Github, Google } from 'lucide-svelte';
    import { login, register, oauthLogin, auth } from '$lib/auth.svelte.ts';

    let username = '';
    let password = '';
    let email = '';
    let isLogin = true;
    let errorMessage = '';
    let isLoading = false;

    // OAuth configuration
    const oauthProviders = {
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

    onMount(() => {
        // Check if user is already logged in
        auth.subscribe(value => {
            if (value.isAuthenticated) {
                goto('/');
            }
        });
    });

    async function handleSubmit() {
        isLoading = true;
        errorMessage = '';
        
        try {
            if (isLogin) {
                // Login
                const success = await login(username, password);
                
                if (!success) {
                    throw new Error('Login failed. Please check your credentials.');
                }
                
                goto('/');
            } else {
                // Register
                const success = await register(email, username, password);
                
                if (!success) {
                    throw new Error('Registration failed. Username or email may already be in use.');
                }
                
                // Switch to login form after successful registration
                isLogin = true;
                errorMessage = 'Registration successful! Please log in.';
            }
        } catch (error) {
            errorMessage = error.message;
        } finally {
            isLoading = false;
        }
    }

    function handleOAuthLogin(provider) {
        const config = oauthProviders[provider];
        if (!config) return;
        
        const params = new URLSearchParams({
            client_id: config.clientId,
            redirect_uri: config.redirectUri,
            response_type: 'code',
            scope: config.scope,
            state: provider // We'll use this to identify the provider in the callback
        });
        
        window.location.href = `${config.authUrl}?${params.toString()}`;
    }

    function toggleForm() {
        isLogin = !isLogin;
        errorMessage = '';
    }
</script>

<div class="login-container">
    <div class="login-card">
        <h1>{isLogin ? 'Login' : 'Register'}</h1>
        
        {#if errorMessage}
            <div class="error-message">{errorMessage}</div>
        {/if}
        
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
                        required
                        placeholder="Enter your email"
                    />
                </div>
            {/if}
            
            <div class="form-group">
                <label for="username">
                    <User size={20} />
                    Username
                </label>
                <input 
                    type="text" 
                    id="username" 
                    bind:value={username} 
                    required
                    placeholder="Enter your username"
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
            
            <button type="submit" class="primary-button" disabled={isLoading}>
                {isLoading ? 'Loading...' : isLogin ? 'Login' : 'Register'}
            </button>
        </form>
        
        <div class="divider">
            <span>OR</span>
        </div>
        
        <div class="oauth-buttons">
            <button 
                class="oauth-button google" 
                on:click={() => handleOAuthLogin('google')}
                disabled={isLoading}
            >
                <Google size={20} />
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
        
        <div class="toggle-form">
            {isLogin ? "Don't have an account?" : "Already have an account?"}
            <button class="text-button" on:click={toggleForm}>
                {isLogin ? 'Register' : 'Login'}
            </button>
        </div>
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
    
    .primary-button {
        width: 100%;
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
    
    .toggle-form {
        margin-top: 24px;
        text-align: center;
        color: #555;
    }
    
    .text-button {
        background: none;
        border: none;
        color: #4a90e2;
        font-weight: 500;
        cursor: pointer;
        padding: 0;
        font-size: inherit;
    }
    
    .text-button:hover {
        text-decoration: underline;
    }
    
    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 10px;
        border-radius: 4px;
        margin-bottom: 20px;
        text-align: center;
    }
</style>
