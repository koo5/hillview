<script lang="ts">
    import { onMount } from 'svelte';
    import { myGoto } from '$lib/navigation.svelte';
    import { User, Mail, Calendar, Trash2, LogOut, Settings, Shield } from 'lucide-svelte';
    import BackButton from '../../components/BackButton.svelte';
    import { auth, logout } from '$lib/auth.svelte';
    import { invoke } from '@tauri-apps/api/core';
    import { http, handleApiError, TokenExpiredError } from '$lib/http';

    let userInfo: any = null;
    let isLoading = true;
    let errorMessage = '';
    let successMessage = '';
    let showDeleteConfirm = false;
    let deleteConfirmText = '';

    onMount(async () => {
        await loadUserProfile();
    });

    async function loadUserProfile() {
        isLoading = true;
        errorMessage = '';

        try {
            const response = await http.get('/user/profile');

            if (!response.ok) {
                throw new Error(`Failed to load profile: ${response.status}`);
            }

            userInfo = await response.json();
        } catch (error) {
            console.error('🢄Error loading profile:', error);
            errorMessage = handleApiError(error);
            
            // TokenExpiredError is handled automatically by the http client
            // which will call logout and redirect, but we can also check here
            if (error instanceof TokenExpiredError) {
                myGoto('/login');
            }
        } finally {
            isLoading = false;
        }
    }

    async function handleLogout() {
        try {
            await logout();
            myGoto('/');
        } catch (error) {
            console.error('🢄Logout error:', error);
            errorMessage = 'Failed to logout properly';
        }
    }

    async function handleDeleteAccount() {
        if (deleteConfirmText !== 'DELETE') {
            errorMessage = 'Please type "DELETE" to confirm account deletion';
            return;
        }

        try {
            const response = await http.delete('/user/delete');

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to delete account');
            }

            successMessage = 'Account deleted successfully. You will be redirected...';
            
            // Clear authentication and redirect after a delay
            setTimeout(async () => {
                await logout();
                myGoto('/');
            }, 2000);

        } catch (error) {
            console.error('🢄Delete account error:', error);
            errorMessage = handleApiError(error);
        }
    }

    function formatDate(dateString: string) {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
</script>

<div class="profile-container page-scrollable">
    <div class="back-button-container">
        <BackButton title="Back to Map" />
    </div>

    <div class="profile-card">
        <div class="profile-header">
            <div class="profile-icon">
                <User size={48} />
            </div>
            <h1>User Profile</h1>
        </div>

        {#if errorMessage}
            <div class="error-message">{errorMessage}</div>
        {/if}

        {#if successMessage}
            <div class="success-message">{successMessage}</div>
        {/if}

        {#if isLoading}
            <div class="loading">
                <div class="loading-spinner"></div>
                <p>Loading profile...</p>
            </div>
        {:else if userInfo}
            <div class="profile-content">
                <div class="info-section">
                    <h2><User size={20} /> Account Information</h2>
                    
                    <div class="info-grid">
                        <div class="info-item">
                            <User size={16} />
                            <span class="label">Username:</span>
                            <span class="value">{userInfo.username}</span>
                        </div>
                        
                        {#if userInfo.email}
                            <div class="info-item">
                                <Mail size={16} />
                                <span class="label">Email:</span>
                                <span class="value">{userInfo.email}</span>
                            </div>
                        {/if}

                        <div class="info-item">
                            <Calendar size={16} />
                            <span class="label">Member since:</span>
                            <span class="value">{formatDate(userInfo.created_at)}</span>
                        </div>

                        {#if userInfo.provider}
                            <div class="info-item">
                                <Shield size={16} />
                                <span class="label">Login method:</span>
                                <span class="value oauth-badge">{userInfo.provider} OAuth</span>
                            </div>
                        {:else}
                            <div class="info-item">
                                <Shield size={16} />
                                <span class="label">Login method:</span>
                                <span class="value">Username & Password</span>
                            </div>
                        {/if}

                        <div class="info-item">
                            <Settings size={16} />
                            <span class="label">Account status:</span>
                            <span class="value status {userInfo.is_active ? 'active' : 'inactive'}">
                                {userInfo.is_active ? 'Active' : 'Inactive'}
                            </span>
                        </div>
                    </div>
                </div>

                <div class="actions-section">
                    <h2><Settings size={20} /> Account Actions</h2>
                    
                    <div class="action-buttons">
                        <button class="action-button logout" on:click={handleLogout}>
                            <LogOut size={20} />
                            Sign Out
                        </button>
                        
                        <button 
                            class="action-button delete" 
                            on:click={() => showDeleteConfirm = true}
                        >
                            <Trash2 size={20} />
                            Delete Account
                        </button>
                    </div>
                </div>

                {#if showDeleteConfirm}
                    <!-- svelte-ignore a11y-click-events-have-key-events -->
                    <!-- svelte-ignore a11y-no-static-element-interactions -->
                    <div class="delete-confirm-overlay" on:click={() => showDeleteConfirm = false} on:keydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}>
                        <div class="delete-confirm-modal" role="dialog" tabindex="-1" on:click|stopPropagation>
                            <h3><Trash2 size={24} /> Delete Account</h3>
                            <p class="warning">
                                <strong>Warning:</strong> This action cannot be undone. 
                                All your data will be permanently deleted.
                            </p>
                            
                            <div class="confirm-input">
                                <label for="delete-confirm">
                                    Type <strong>DELETE</strong> to confirm:
                                </label>
                                <input 
                                    type="text" 
                                    id="delete-confirm"
                                    bind:value={deleteConfirmText}
                                    placeholder="Type DELETE here"
                                />
                            </div>

                            <div class="modal-actions">
                                <button 
                                    class="cancel-button" 
                                    on:click={() => showDeleteConfirm = false}
                                >
                                    Cancel
                                </button>
                                <button 
                                    class="delete-button" 
                                    on:click={handleDeleteAccount}
                                    disabled={deleteConfirmText !== 'DELETE'}
                                >
                                    <Trash2 size={16} />
                                    Delete Account
                                </button>
                            </div>
                        </div>
                    </div>
                {/if}
            </div>
        {/if}
    </div>
</div>

<style>
    .profile-container {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        background-color: #f5f5f5;
        padding: 20px;
    }

    .back-button-container {
        margin-bottom: 20px;
    }

    .profile-card {
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        padding: 30px;
        max-width: 600px;
        margin: 0 auto;
        width: 100%;
    }

    .profile-header {
        text-align: center;
        margin-bottom: 30px;
        padding-bottom: 20px;
        border-bottom: 1px solid #eee;
    }

    .profile-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 80px;
        height: 80px;
        background-color: #4a90e2;
        color: white;
        border-radius: 50%;
        margin-bottom: 15px;
    }

    h1 {
        margin: 0;
        color: #333;
        font-size: 28px;
    }

    h2 {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #555;
        font-size: 18px;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 1px solid #eee;
    }

    .info-section {
        margin-bottom: 30px;
    }

    .info-grid {
        display: flex;
        flex-direction: column;
        gap: 15px;
    }

    .info-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 0;
    }

    .info-item :global(svg) {
        color: #4a90e2;
        flex-shrink: 0;
    }

    .label {
        font-weight: 500;
        color: #555;
        min-width: 120px;
    }

    .value {
        color: #333;
        flex: 1;
    }

    .oauth-badge {
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 0.9em;
        font-weight: 500;
    }

    .status.active {
        color: #2e7d32;
        font-weight: 500;
    }

    .status.inactive {
        color: #d32f2f;
        font-weight: 500;
    }

    .actions-section {
        margin-top: 30px;
    }

    .action-buttons {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .action-button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 12px 20px;
        border: none;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.3s;
    }

    .action-button.logout {
        background-color: #f5f5f5;
        color: #555;
        border: 1px solid #ddd;
    }

    .action-button.logout:hover {
        background-color: #e5e5e5;
    }

    .action-button.delete {
        background-color: #ffebee;
        color: #d32f2f;
        border: 1px solid #ffcdd2;
    }

    .action-button.delete:hover {
        background-color: #ffcdd2;
    }

    .delete-confirm-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    }

    .delete-confirm-modal {
        background: white;
        border-radius: 12px;
        padding: 30px;
        max-width: 400px;
        width: 90%;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    }

    .delete-confirm-modal h3 {
        display: flex;
        align-items: center;
        gap: 10px;
        color: #d32f2f;
        margin-bottom: 15px;
    }

    .warning {
        color: #666;
        line-height: 1.5;
        margin-bottom: 20px;
    }

    .confirm-input {
        margin-bottom: 25px;
    }

    .confirm-input label {
        display: block;
        margin-bottom: 8px;
        color: #555;
        font-weight: 500;
    }

    .confirm-input input {
        width: 100%;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
    }

    .modal-actions {
        display: flex;
        gap: 12px;
        justify-content: flex-end;
    }

    .cancel-button {
        padding: 10px 20px;
        background-color: #f5f5f5;
        color: #555;
        border: 1px solid #ddd;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
    }

    .cancel-button:hover {
        background-color: #e5e5e5;
    }

    .delete-button {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 20px;
        background-color: #d32f2f;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 500;
        transition: background-color 0.3s;
    }

    .delete-button:hover:not(:disabled) {
        background-color: #b71c1c;
    }

    .delete-button:disabled {
        background-color: #ccc;
        cursor: not-allowed;
    }

    .loading {
        text-align: center;
        padding: 40px 0;
    }

    .loading-spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #4a90e2;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 20px;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 20px;
        text-align: center;
    }

    .success-message {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 20px;
        text-align: center;
    }

    @media (max-width: 768px) {
        .profile-card {
            padding: 20px;
            margin: 0;
        }

        .info-item {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }

        .label {
            min-width: auto;
            font-size: 0.9em;
        }

        .action-buttons {
            gap: 15px;
        }
    }
</style>