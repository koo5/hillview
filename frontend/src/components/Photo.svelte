<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { EyeOff, UserX, ThumbsUp, ThumbsDown, Share } from 'lucide-svelte';
    import { app } from '$lib/data.svelte';
    import { auth } from '$lib/auth.svelte';
    import { http, handleApiError } from '$lib/http';
    import { myGoto } from '$lib/navigation.svelte';
    import { constructUserProfileUrl, constructShareUrl } from '$lib/urlUtils';
    import { TAURI } from '$lib/tauri.js';
    import { invoke } from '@tauri-apps/api/core';
    import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
    import { simplePhotoWorker } from '$lib/simplePhotoWorker';
    import type { PhotoData } from '$lib/sources';

    export let photo: PhotoData | null = null;
    export let className = '';
    export let clientWidth: number | undefined = undefined;

    let clientWidth2: number | undefined;

    let fetchPriority = className === 'front' ? 'high' : 'auto';

    let containerElement: HTMLElement | undefined;
    let selectedUrl: string | undefined;
    let selectedSize: any;
    let width = 100;
    let height = 100;
    let devicePhotoUrl: string | null = null;
    let bg_style_stretched_photo;
    let border_style;

    // Background loading state
    let displayedUrl: string | undefined;
    let isLoadingNewImage = false;
    let preloadImg: HTMLImageElement | null = null;

    // Hide functionality state
    let showHideUserDialog = false;
    let hideUserReason = '';
    let flagUserForReview = false;
    let isHiding = false;
    let hideMessage = '';

    // Rating functionality state
    let userRating: 'thumbs_up' | 'thumbs_down' | null = null;
    let ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
    let isRating = false;

    // Get current user authentication state
    $: isAuthenticated = $auth.isAuthenticated;

    // enable for stretched backdrop
    //$: bg_style_stretched_photo = photo.sizes?.[50] ? `background-image: url(${photo.sizes[50].url});` : ''

    $: border_style = className === 'front' && photo ? 'border: 4px dotted #4a90e2;' : '';
    //console.log('🢄border_style:', border_style);

    $: if (photo || clientWidth || containerElement) updateSelectedUrl();

    // Handle selectedUrl changes with background loading
    $: if (selectedUrl !== undefined && selectedUrl !== displayedUrl) {
        handleImageChange(selectedUrl);
    }

    async function updateSelectedUrl() {

        if (clientWidth)
            clientWidth2 = clientWidth;
        else
            if (!clientWidth2)
                clientWidth2 = 500;

        //console.log('🢄updateSelectedUrl clientWidth:', clientWidth2);

        if (!containerElement) {
            return;
        }

        if (!photo) {
            selectedUrl = '';
            devicePhotoUrl = null;
            return;
        }

        // Handle device photos specially
        if (photo.isDevicePhoto && photo.url) {
            try {
                devicePhotoUrl = await getDevicePhotoUrl(photo.url);
                selectedUrl = devicePhotoUrl;
                return;
            } catch (error) {
                console.error('🢄Failed to load device photo:', error);
                selectedUrl = '';
                return;
            }
        }

        if (!photo.sizes) {
            selectedUrl = photo.url;
            return;
        }

        // Find the best scaled version based on container width. Take the 'full' size if this fails
        const sizes = Object.keys(photo.sizes).filter(size => size !== 'full').sort((a, b) => Number(a) - Number(b));
        let p: any;
        for (let i = 0; i < sizes.length; i++) {
            const size = sizes[i];
            //console.log('🢄size:', size);
            if (Number(size) >= clientWidth2 || ((i === sizes.length - 1) && !photo.sizes.full)) {
                p = photo.sizes[sizes[i]];
                selectedSize = size;
                width = p.width;
                height = p.height;

                // Handle device photo URLs
                if (photo.isDevicePhoto) {
                    selectedUrl = await getDevicePhotoUrl(p.url);
                } else {
                    selectedUrl = p.url;
                }
                return;
            }
        }
        selectedSize = 'full';
        width = photo.sizes.full?.width || p?.width || 0;
        height = photo.sizes.full?.height || p?.height || 0;

        // Handle device photo URLs for full size
        if (photo.isDevicePhoto && photo.sizes.full) {
            selectedUrl = await getDevicePhotoUrl(photo.sizes.full.url);
        } else {
            selectedUrl = photo.sizes.full?.url || '';
        }
    }

    async function handleImageChange(newUrl: string) {
        if (!newUrl || newUrl === displayedUrl) {
            return;
        }

        // If this is the first image or no previous image, show immediately
        if (!displayedUrl) {
            displayedUrl = newUrl;
            return;
        }

        // Start background loading
        isLoadingNewImage = true;

        try {
            preloadImg = new Image();

            preloadImg.onload = () => {
                displayedUrl = newUrl;
                isLoadingNewImage = false;
                preloadImg = null;
            };

            preloadImg.onerror = () => {
                console.error('Failed to preload image:', newUrl);
                isLoadingNewImage = false;
                preloadImg = null;
            };

            preloadImg.src = newUrl;

        } catch (error) {
            console.error('Error preloading image:', error);
            isLoadingNewImage = false;
        }
    }

    // Helper functions to determine photo source and get user info
    function getPhotoSource(photo: PhotoData): string {
		if (!photo?.source?.id) throw new Error('Photo source information is missing');
        return photo.source.id;
    }

    function getUserId(photo: PhotoData): string | null {
        if (!photo) return null;

        // For Mapillary photos, check if creator info exists in the photo data
        if ((photo as any).creator?.id) {
            return (photo as any).creator.id;
        }
        // For Hillview photos, check for owner_id field
        if ((photo as any).owner_id) {
            return (photo as any).owner_id;
        }
        return null;
    }

    function getUserName(photo: PhotoData): string | null {
        if (!photo) return null;

        // For Mapillary photos, check if creator info exists in the photo data
        if ((photo as any).creator?.username) {
            return (photo as any).creator.username;
        }
        // For Hillview photos, check for owner_username field
        if ((photo as any).owner_username) {
            return (photo as any).owner_username;
        }
        return null;
    }

    async function hidePhoto() {
        if (!photo || !isAuthenticated || isHiding) return;

        isHiding = true;
        hideMessage = '';

        try {
            const photoSource = getPhotoSource(photo);
            const response = await http.post('/hidden/photos', {
                photo_source: photoSource,
                photo_id: photo.id,
                reason: 'Hidden from gallery'
            });

            if (!response.ok) {
                throw new Error(`Failed to hide photo: ${response.status}`);
            }

            // Call webworker to remove from cache
            simplePhotoWorker.removePhotoFromCache?.(photo.id, photoSource);

            hideMessage = 'Photo hidden successfully';
            setTimeout(() => hideMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error hiding photo:', error);
            hideMessage = `Error: ${handleApiError(error)}`;
            setTimeout(() => hideMessage = '', 5000);
        } finally {
            isHiding = false;
        }
    }

    function showUserHideDialog() {
        if (!photo || !isAuthenticated) return;

        showHideUserDialog = true;
        hideUserReason = '';
        flagUserForReview = false;
    }

    function cancelHideUser() {
        showHideUserDialog = false;
        hideUserReason = '';
        flagUserForReview = false;
    }

    async function confirmHideUser() {
        if (!photo || !isAuthenticated || isHiding) return;

        const userId = getUserId(photo);
        if (!userId) {
            hideMessage = 'Cannot hide user: User information not available';
            setTimeout(() => hideMessage = '', 5000);
            showHideUserDialog = false;
            return;
        }

        isHiding = true;
        hideMessage = '';

        try {
            const photoSource = getPhotoSource(photo);
            const requestBody: any = {
                target_user_source: photoSource,
                target_user_id: userId,
                reason: hideUserReason || 'Hidden from gallery'
            };

            // Add metadata if user should be flagged for review
            if (flagUserForReview) {
                requestBody.extra_data = { flagged_for_review: true };
            }

            const response = await http.post('/hidden/users', requestBody);

            if (!response.ok) {
                throw new Error(`Failed to hide user: ${response.status}`);
            }

            // Call webworker to remove all photos by this user from cache
            simplePhotoWorker.removeUserPhotosFromCache?.(userId, photoSource);

            hideMessage = 'User hidden successfully';
            setTimeout(() => hideMessage = '', 2000);
            showHideUserDialog = false;
        } catch (error) {
            console.error('🢄Error hiding user:', error);
            hideMessage = `Error: ${handleApiError(error)}`;
            setTimeout(() => hideMessage = '', 5000);
        } finally {
            isHiding = false;
        }
    }

    // Rating functionality
    async function handleRatingClick(rating: 'thumbs_up' | 'thumbs_down') {
        if (!photo || !isAuthenticated || isRating) return;

        const photoSource = getPhotoSource(photo);
        isRating = true;

        try {
            let response;

            if (userRating === rating) {
                // Remove rating if clicking the same rating
                response = await http.delete(`/ratings/${photoSource}/${photo.id}`);
                userRating = null;
            } else {
                // Set new rating
                response = await http.post(`/ratings/${photoSource}/${photo.id}`, {
                    rating: rating
                });
                const data = await response.json();
                userRating = data.user_rating as 'thumbs_up' | 'thumbs_down' | null;
                ratingCounts = data.rating_counts;
            }

            if (!response.ok) {
                throw new Error(`Failed to update rating: ${response.status}`);
            }

            // If we removed a rating, get updated counts
            if (!userRating) {
                const getRatingResponse = await http.get(`/ratings/${photoSource}/${photo.id}`);
                if (getRatingResponse.ok) {
                    const data = await getRatingResponse.json();
                    ratingCounts = data.rating_counts;
                }
            }
        } catch (error) {
            console.error('🢄Error updating rating:', error);
            hideMessage = `Rating error: ${handleApiError(error)}`;
            setTimeout(() => hideMessage = '', 3000);
        } finally {
            isRating = false;
        }
    }

    // Load rating data when photo changes
    async function loadPhotoRating() {
        if (!photo || !isAuthenticated) {
            userRating = null;
            ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
            return;
        }

        try {
            const photoSource = getPhotoSource(photo);
            const response = await http.get(`/ratings/${photoSource}/${photo.id}`);

            if (response.ok) {
                const data = await response.json();
                userRating = data.user_rating;
                ratingCounts = data.rating_counts || { thumbs_up: 0, thumbs_down: 0 };
            } else {
                // If rating endpoint fails, set defaults
                userRating = null;
                ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
            }
        } catch (error) {
            console.error('🢄Error loading rating:', error);
            userRating = null;
            ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
        }
    }

    // Load rating when photo changes
    $: if (photo && isAuthenticated) {
        loadPhotoRating();
    }

    // Navigate to user profile for Hillview photos
    function viewUserProfile() {
        if (!photo) return;

        const photoSource = getPhotoSource(photo);
        const userId = getUserId(photo);

        if (photoSource === 'hillview' && userId) {
            myGoto(constructUserProfileUrl(userId));
        }
    }

    // Share photo functionality
    async function sharePhoto() {
        if (!photo) return;

        try {
            const shareUrl = constructShareUrl(photo);
            const shareText = `Check out this photo on Hillview${getUserName(photo) ? ` by @${getUserName(photo)}` : ''}`;

            if (TAURI) {
                // Use native Android sharing through Tauri plugin
                const result = await invoke('plugin:hillview|share_photo', {
                    title: 'Photo on Hillview',
                    text: shareText,
                    url: shareUrl
                }) as { success: boolean; error?: string; message?: string };

                if (result.success) {
                    hideMessage = 'Shared successfully!';
                    setTimeout(() => hideMessage = '', 2000);
                } else {
                    throw new Error(result.error || 'Share failed');
                }
            } else {
                // Web fallback - copy to clipboard
                if (navigator.clipboard) {
                    const fullShareText = `${shareText}\n${shareUrl}`;
                    await navigator.clipboard.writeText(fullShareText);
                    hideMessage = 'Share link copied to clipboard!';
                    setTimeout(() => hideMessage = '', 2000);
                } else {
                    // Fallback for older browsers
                    const textarea = document.createElement('textarea');
                    textarea.value = `${shareText}\n${shareUrl}`;
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    hideMessage = 'Share link copied to clipboard!';
                    setTimeout(() => hideMessage = '', 2000);
                }
            }
        } catch (error) {
            console.error('🢄Error sharing photo:', error);
            hideMessage = 'Failed to share photo';
            setTimeout(() => hideMessage = '', 3000);
        }
    }



</script>
{#if $app.debug === 5}
    <div class="debug">
        <b>Debug Information</b><br>
        <b>clientWidth2:</b> {clientWidth2}<br>
        <b>Selected URL:</b> {JSON.stringify(selectedUrl)}<br>
        <b>Selected Size:</b> {selectedSize}
        <b>Width:</b> {width}
        <b>Height:</b> {height}
        <b>Photo:</b> <pre>{JSON.stringify(photo, null, 2)}</pre>
    </div>
{/if}


<div bind:this={containerElement} class="photo-wrapper" >

    {#if photo && displayedUrl}
        <img
            src={displayedUrl}
            alt={photo.file}
            class="{className} photo"
            style="{bg_style_stretched_photo} {border_style}"
            fetchpriority={fetchPriority as any}
            data-testid="main-photo"
            data-photo={JSON.stringify(photo)}
        />

        <!-- Loading spinner overlay -->
        {#if isLoadingNewImage}
            <div class="photo-loading-overlay" data-testid="photo-loading-spinner">
                <!-- Import spinner here since we don't want to import the full Spinner component -->
                <div class="photo-spinner"></div>
            </div>
        {/if}

        <!-- Hide buttons for front photo only, and only for authenticated users -->
        {#if className === 'front' && isAuthenticated}
            <!-- Creator username display -->
            {#if getUserName(photo)}
                <div class="creator-info">
                    {#if getPhotoSource(photo) === 'hillview'}
                        <button class="creator-name clickable" on:click={viewUserProfile}>
                            @{getUserName(photo)}
                        </button>
                    {:else}
                        <span class="creator-name">@{getUserName(photo)}</span>
                    {/if}
                    <span class="source-name">{getPhotoSource(photo)}</span>
                </div>
            {/if}

            <div class="hide-buttons">

                <!-- Share button -->
                <button
                    class="hide-button share-button"
                    on:click={sharePhoto}
                    title="Share photo"
                    data-testid="share-button"
                >
                    <Share size={16} />
                </button>

                <!-- Rating buttons -->
                <button
                    class="hide-button rating-button {userRating === 'thumbs_up' ? 'active' : ''}"
                    on:click={() => handleRatingClick('thumbs_up')}
                    disabled={isRating}
                    title="Thumbs up"
                    data-testid="thumbs-up-button"
                >
                    <ThumbsUp size={16} />
                    <span class="rating-count">{ratingCounts.thumbs_up}</span>
                </button>

                <button
                    class="hide-button rating-button {userRating === 'thumbs_down' ? 'active' : ''}"
                    on:click={() => handleRatingClick('thumbs_down')}
                    disabled={isRating}
                    title="Thumbs down"
                    data-testid="thumbs-down-button"
                >
                    <ThumbsDown size={16} />
                    <span class="rating-count">{ratingCounts.thumbs_down}</span>
                </button>

                <button
                    class="hide-button hide-photo"
                    on:click={hidePhoto}
                    disabled={isHiding}
                    title="Hide this photo"
                    data-testid="hide-photo-button"
                >
                    <EyeOff size={16} />
                </button>

                <button
                    class="hide-button hide-user"
                    on:click={showUserHideDialog}
                    disabled={isHiding || !getUserId(photo)}
                    title="Hide all photos by {getUserName(photo) || 'this user'}"
                    data-testid="hide-user-button"
                >
                    <UserX size={16} />
                </button>
            </div>
        {/if}

        <!-- Status message -->
        {#if hideMessage}
            <div class="hide-message" class:error={hideMessage.startsWith('Error')}>
                {hideMessage}
            </div>
        {/if}
    {/if}
</div>

<!-- Hide User Confirmation Dialog -->
{#if showHideUserDialog}
    <div class="dialog-overlay">
        <div class="dialog">
            <h3>Hide User</h3>
            <p>This will hide all photos by <strong>{photo && getUserName(photo) ? `@${getUserName(photo)}` : 'this user'}</strong> from your view.</p>

            <div class="form-group">
                <label for="hide-reason">Reason (optional):</label>
                <input
                    id="hide-reason"
                    type="text"
                    bind:value={hideUserReason}
                    placeholder="e.g., Inappropriate content, spam, etc."
                    maxlength="100"
                />
            </div>

            <div class="form-group">
                <label class="checkbox-label">
                    <input
                        type="checkbox"
                        bind:checked={flagUserForReview}
                    />
                    Flag user for review by moderators
                </label>
            </div>

            <div class="dialog-buttons">
                <button
                    class="cancel-button"
                    on:click={cancelHideUser}
                    disabled={isHiding}
                >
                    Cancel
                </button>
                <button
                    class="confirm-button"
                    on:click={confirmHideUser}
                    disabled={isHiding}
                >
                    {isHiding ? 'Hiding...' : 'Hide User'}
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    .debug {
        overflow: auto;
        position: absolute;
        top: 130;
        left: 100;
        padding: 0.5rem;
        background: #f0f070;
        border: 1px solid black;
        z-index: 1000;
        width: 320px; /* Fixed width */
        height: 320px; /* Fixed height */
    }
    .photo-wrapper {
        display: flex;
        justify-content: center;
        /*width: 100%;*/
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        background-repeat: no-repeat;

    }

    .photo {
        object-fit: contain;
        background-size: cover;
        -o-background-size: cover;
    }


    /* Front image is centered and on top */
    .front {
        z-index: 2;
    }

    /* Side images are absolutely positioned and vertically centered */
    .left {
        opacity: 0.4;
        position: absolute;
        top: 50%;
        transform: translateY(-80%);
        z-index: 1;
        /* Optionally, set a width to control how much of the side image shows */
        width: 90%;
        left: 0;
        mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
    }

    .right {
        opacity: 0.4;
        position: absolute;
        top: 50%;
        transform: translateY(-20%);
        z-index: 1;
        /* Optionally, set a width to control how much of the side image shows */
        width: 90%;
        right: 0;
        mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
    }

    /* Creator info display */
    .creator-info {
        position: absolute;
        bottom: 60px;
        right: 10px;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 6px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        z-index: 9;
        max-width: 150px;
        text-align: right;
    }

    .creator-name {
        color: #4a90e2;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }

    .creator-name.clickable {
        background: none;
        border: none;
        padding: 0;
        margin: 0;
        font-size: inherit;
        font-weight: inherit;
        font-family: inherit;
        color: #4a90e2;
        cursor: pointer;
        text-decoration: underline;
        transition: color 0.2s ease;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }

    .creator-name.clickable:hover {
        color: #357abd;
    }

    .source-name {
        color: rgba(255, 255, 255, 0.7);
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Hide buttons */
    .hide-buttons {
        position: absolute;
        bottom: 10px;
        right: 10px;
        display: flex;
        gap: 6px;
        z-index: 10;
    }

    .hide-button {
        background: rgba(0, 0, 0, 0.7);
        color: white;
        border: none;
        border-radius: 50%;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }

    .hide-button:hover:not(:disabled) {
        background: rgba(0, 0, 0, 0.9);
        transform: scale(1.1);
    }

    .hide-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        transform: none;
    }

    .hide-photo {
        background: rgba(220, 53, 69, 0.8);
    }

    .hide-photo:hover:not(:disabled) {
        background: rgba(220, 53, 69, 1);
    }

    .hide-user {
        background: rgba(255, 133, 27, 0.8);
    }

    .hide-user:hover:not(:disabled) {
        background: rgba(255, 133, 27, 1);
    }

    /* Rating buttons */
    .rating-button {
        background: rgba(0, 0, 0, 0.7);
        color: white;
        position: relative;
        width: auto !important;
        min-width: 40px;
        padding: 0 8px;
        border-radius: 18px !important;
        gap: 4px;
    }

    .rating-button:hover:not(:disabled) {
        background: rgba(0, 0, 0, 0.9);
    }

    .rating-button.active {
        background: rgba(40, 167, 69, 0.8);
        color: white;
    }

    .rating-button.active:hover:not(:disabled) {
        background: rgba(40, 167, 69, 1);
    }

    .rating-count {
        font-size: 12px;
        font-weight: 600;
        min-width: 12px;
        text-align: center;
    }

    /* Share button */
    .share-button {
        background: rgba(74, 144, 226, 0.8);
    }

    .share-button:hover:not(:disabled) {
        background: rgba(74, 144, 226, 1);
    }

    /* Status message */
    .hide-message {
        position: absolute;
        bottom: 60px;
        right: 10px;
        background: rgba(40, 167, 69, 0.9);
        color: white;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        z-index: 10;
        animation: fadeIn 0.3s ease;
    }

    .hide-message.error {
        background: rgba(220, 53, 69, 0.9);
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Dialog styles */
    .dialog-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        animation: fadeIn 0.2s ease;
    }

    .dialog {
        background: white;
        padding: 24px;
        border-radius: 12px;
        max-width: 400px;
        width: 90%;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        animation: slideIn 0.2s ease;
    }

    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(-20px) scale(0.95);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    .dialog h3 {
        margin: 0 0 16px 0;
        color: #333;
        font-size: 1.25rem;
    }

    .dialog p {
        margin: 0 0 20px 0;
        color: #666;
        line-height: 1.4;
    }

    .form-group {
        margin-bottom: 16px;
    }

    .form-group label {
        display: block;
        margin-bottom: 6px;
        color: #333;
        font-weight: 500;
    }

    .form-group input[type="text"] {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 14px;
        box-sizing: border-box;
    }

    .form-group input[type="text"]:focus {
        outline: none;
        border-color: #4a90e2;
        box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.2);
    }

    .checkbox-label {
        display: flex !important;
        align-items: center;
        gap: 8px;
        cursor: pointer;
    }

    .checkbox-label input[type="checkbox"] {
        width: auto;
        margin: 0;
    }

    .dialog-buttons {
        display: flex;
        gap: 12px;
        justify-content: flex-end;
        margin-top: 24px;
    }

    .dialog-buttons button {
        padding: 10px 20px;
        border: none;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .cancel-button {
        background: #f8f9fa;
        color: #495057;
        border: 1px solid #dee2e6;
    }

    .cancel-button:hover:not(:disabled) {
        background: #e9ecef;
    }

    .confirm-button {
        background: #ff851b;
        color: white;
    }

    .confirm-button:hover:not(:disabled) {
        background: #e76500;
    }

    .dialog-buttons button:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    /* Photo loading overlay */
    .photo-loading-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        /*background-color: rgba(0, 0, 0, 0.3);*/
        z-index: 8;
        pointer-events: none;
    }

    /* Simple spinner animation */
    .photo-spinner {
        width: 40px;
        height: 40px;
        border: 4px solid rgba(255, 255, 255, 0.3);
        border-top: 4px solid #ffffff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

</style>
