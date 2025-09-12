<script lang="ts">
    import { onMount } from 'svelte';
    import { myGoto } from '$lib/navigation.svelte';
    import { EyeOff, Trash2, User, Image, MapPin } from 'lucide-svelte';
    import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
    import StandardBody from '../../components/StandardBody.svelte';
    import { auth } from '$lib/auth.svelte';
    import { http, handleApiError, TokenExpiredError } from '$lib/http';

    interface HiddenPhoto {
        photo_source: 'mapillary' | 'hillview';
        photo_id: string;
        hidden_at: string;
        reason?: string;
    }

    interface HiddenUser {
        target_user_source: 'mapillary' | 'hillview';
        target_user_id: string;
        hidden_at: string;
        reason?: string;
    }

    let hiddenPhotos: HiddenPhoto[] = [];
    let hiddenUsers: HiddenUser[] = [];
    let isLoading = true;
    let errorMessage = '';
    let successMessage = '';
    let activeTab: 'photos' | 'users' = 'photos';

    onMount(async () => {
        // Check if user is authenticated
        if (!$auth.isAuthenticated) {
            myGoto('/login');
            return;
        }
        
        await loadHiddenContent();
    });

    async function loadHiddenContent() {
        isLoading = true;
        errorMessage = '';
        successMessage = '';

        try {
            // Load hidden photos and users in parallel
            const [photosResponse, usersResponse] = await Promise.all([
                http.get('/hidden/photos'),
                http.get('/hidden/users')
            ]);

            if (!photosResponse.ok) {
                throw new Error(`Failed to load hidden photos: ${photosResponse.status}`);
            }
            if (!usersResponse.ok) {
                throw new Error(`Failed to load hidden users: ${usersResponse.status}`);
            }

            hiddenPhotos = await photosResponse.json();
            hiddenUsers = await usersResponse.json();
        } catch (error) {
            console.error('🢄Error loading hidden content:', error);
            errorMessage = handleApiError(error);
            
            if (error instanceof TokenExpiredError) {
                myGoto('/login');
            }
        } finally {
            isLoading = false;
        }
    }

    async function unhidePhoto(photo: HiddenPhoto) {
        try {
            const response = await http.delete('/hidden/photos', {
                photo_source: photo.photo_source,
                photo_id: photo.photo_id
            });

            if (!response.ok) {
                throw new Error(`Failed to unhide photo: ${response.status}`);
            }

            // Remove from local state
            hiddenPhotos = hiddenPhotos.filter(p => 
                !(p.photo_source === photo.photo_source && p.photo_id === photo.photo_id)
            );
            successMessage = 'Photo unhidden successfully';
            setTimeout(() => successMessage = '', 3000);
        } catch (error) {
            console.error('🢄Error unhiding photo:', error);
            errorMessage = handleApiError(error);
            setTimeout(() => errorMessage = '', 5000);
        }
    }

    async function unhideUser(user: HiddenUser) {
        try {
            const response = await http.delete('/hidden/users', {
                target_user_source: user.target_user_source,
                target_user_id: user.target_user_id
            });

            if (!response.ok) {
                throw new Error(`Failed to unhide user: ${response.status}`);
            }

            // Remove from local state
            hiddenUsers = hiddenUsers.filter(u => 
                !(u.target_user_source === user.target_user_source && u.target_user_id === user.target_user_id)
            );
            successMessage = 'User unhidden successfully';
            setTimeout(() => successMessage = '', 3000);
        } catch (error) {
            console.error('🢄Error unhiding user:', error);
            errorMessage = handleApiError(error);
            setTimeout(() => errorMessage = '', 5000);
        }
    }

    function formatDate(dateString: string): string {
        return new Date(dateString).toLocaleString();
    }

    function getSourceDisplayName(source: string): string {
        return source === 'mapillary' ? 'Mapillary' : 'My Photos';
    }

    function getSourceIcon(source: string) {
        return source === 'mapillary' ? MapPin : Image;
    }
</script>

<svelte:head>
    <title>Hidden Content - Hillview</title>
</svelte:head>

<StandardHeaderWithAlert 
    title="Hidden Content" 
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>
        
        <div class="description">
            <div class="title-section">
                <EyeOff size={32} />
            </div>
            <p class="subtitle">Manage photos and users you've hidden from your view</p>
        </div>

        {#if errorMessage}
            <div class="error-message" data-testid="error-message">
                {errorMessage}
            </div>
        {/if}

        {#if successMessage}
            <div class="success-message" data-testid="success-message">
                {successMessage}
            </div>
        {/if}

        <div class="tabs">
            <button 
                class="tab-button" 
                class:active={activeTab === 'photos'}
                on:click={() => activeTab = 'photos'}
                data-testid="photos-tab"
            >
                <Image size={18} />
                Hidden Photos ({hiddenPhotos.length})
            </button>
            <button 
                class="tab-button" 
                class:active={activeTab === 'users'}
                on:click={() => activeTab = 'users'}
                data-testid="users-tab"
            >
                <User size={18} />
                Hidden Users ({hiddenUsers.length})
            </button>
        </div>

        {#if isLoading}
            <div class="loading">
                <div class="spinner"></div>
                <p>Loading hidden content...</p>
            </div>
        {:else}
            <div class="content">
                {#if activeTab === 'photos'}
                    <div class="section">
                        <h2>Hidden Photos</h2>
                        {#if hiddenPhotos.length === 0}
                            <div class="empty-state">
                                <EyeOff size={48} />
                                <p>No hidden photos</p>
                                <p class="empty-description">Photos you hide will appear here, and you can unhide them at any time.</p>
                            </div>
                        {:else}
                            <div class="items-list">
                                {#each hiddenPhotos as photo (photo.photo_source + photo.photo_id)}
                                    <div class="item-card" data-testid="hidden-photo-item">
                                        <div class="item-header">
                                            <div class="item-info">
                                                <svelte:component this={getSourceIcon(photo.photo_source)} size={20} />
                                                <div class="item-details">
                                                    <span class="source-name">{getSourceDisplayName(photo.photo_source)}</span>
                                                    <span class="item-id">ID: {photo.photo_id}</span>
                                                </div>
                                            </div>
                                            <button 
                                                class="unhide-button"
                                                on:click={() => unhidePhoto(photo)}
                                                title="Unhide this photo"
                                                data-testid="unhide-photo-button"
                                            >
                                                <Trash2 size={16} />
                                                Unhide
                                            </button>
                                        </div>
                                        <div class="item-meta">
                                            <span class="hidden-date">Hidden on {formatDate(photo.hidden_at)}</span>
                                            {#if photo.reason}
                                                <span class="reason">Reason: {photo.reason}</span>
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {:else}
                    <div class="section">
                        <h2>Hidden Users</h2>
                        {#if hiddenUsers.length === 0}
                            <div class="empty-state">
                                <User size={48} />
                                <p>No hidden users</p>
                                <p class="empty-description">Users you hide will appear here, and you can unhide them to see their photos again.</p>
                            </div>
                        {:else}
                            <div class="items-list">
                                {#each hiddenUsers as user (user.target_user_source + user.target_user_id)}
                                    <div class="item-card" data-testid="hidden-user-item">
                                        <div class="item-header">
                                            <div class="item-info">
                                                <svelte:component this={getSourceIcon(user.target_user_source)} size={20} />
                                                <div class="item-details">
                                                    <span class="source-name">{getSourceDisplayName(user.target_user_source)}</span>
                                                    <span class="item-id">User ID: {user.target_user_id}</span>
                                                </div>
                                            </div>
                                            <button 
                                                class="unhide-button"
                                                on:click={() => unhideUser(user)}
                                                title="Unhide this user's photos"
                                                data-testid="unhide-user-button"
                                            >
                                                <Trash2 size={16} />
                                                Unhide
                                            </button>
                                        </div>
                                        <div class="item-meta">
                                            <span class="hidden-date">Hidden on {formatDate(user.hidden_at)}</span>
                                            {#if user.reason}
                                                <span class="reason">Reason: {user.reason}</span>
                                            {/if}
                                        </div>
                                    </div>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/if}
            </div>
        {/if}
</StandardBody>

<style>


    .title-section {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        margin-bottom: 0.5rem;
    }


    .subtitle {
        color: #666;
        font-size: 1.1rem;
        margin: 0;
    }

    .error-message {
        background-color: #fee;
        color: #c33;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        border: 1px solid #fcc;
    }

    .success-message {
        background-color: #efe;
        color: #3a3;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        border: 1px solid #cfc;
    }

    .tabs {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 2rem;
        border-bottom: 2px solid #f0f0f0;
    }

    .tab-button {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 1rem 1.5rem;
        background: none;
        border: none;
        font-size: 1rem;
        color: #666;
        cursor: pointer;
        border-bottom: 3px solid transparent;
        transition: all 0.2s ease;
    }

    .tab-button:hover {
        color: #4a90e2;
        background-color: #f8f9fa;
    }

    .tab-button.active {
        color: #4a90e2;
        border-bottom-color: #4a90e2;
        font-weight: 600;
    }

    .loading {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
        padding: 4rem 2rem;
        color: #666;
    }

    .spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #f0f0f0;
        border-top: 4px solid #4a90e2;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    .content {
        animation: fadeIn 0.3s ease-in;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .section h2 {
        color: #333;
        margin-bottom: 1.5rem;
        font-size: 1.5rem;
    }

    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: #666;
    }

    .empty-state p {
        margin: 1rem 0 0.5rem;
        font-size: 1.2rem;
    }

    .empty-description {
        font-size: 1rem !important;
        color: #888;
    }

    .items-list {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .item-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        transition: all 0.2s ease;
    }

    .item-card:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        border-color: #4a90e2;
    }

    .item-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 1rem;
    }

    .item-info {
        display: flex;
        align-items: center;
        gap: 1rem;
        flex: 1;
    }

    .item-details {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .source-name {
        font-weight: 600;
        color: #333;
        font-size: 1.1rem;
    }

    .item-id {
        color: #666;
        font-size: 0.9rem;
        font-family: monospace;
    }

    .unhide-button {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: #e53935;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.9rem;
        transition: all 0.2s ease;
    }

    .unhide-button:hover {
        background: #c62828;
        transform: translateY(-1px);
    }

    .item-meta {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        color: #666;
        font-size: 0.9rem;
    }

    .hidden-date {
        font-style: italic;
    }

    .reason {
        color: #888;
    }

    /* Responsive design */
    @media (max-width: 768px) {


        .item-header {
            flex-direction: column;
            gap: 1rem;
        }

        .unhide-button {
            align-self: flex-start;
        }
    }
</style>