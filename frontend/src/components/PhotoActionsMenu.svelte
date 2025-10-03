<script lang="ts">
    import { EyeOff, UserX, ThumbsUp, ThumbsDown, Share, Flag, MoreVertical } from 'lucide-svelte';
    import { http, handleApiError } from '$lib/http';
    import { auth } from '$lib/auth.svelte';
    import { simplePhotoWorker } from '$lib/simplePhotoWorker';
    import { constructUserProfileUrl, constructShareUrl, openExternalUrl } from '$lib/urlUtils';
    import { myGoto } from '$lib/navigation.svelte';
    import { TAURI } from '$lib/tauri.js';
    import { invoke } from '@tauri-apps/api/core';
    import type { PhotoData } from '$lib/sources';

    export let photo: PhotoData | null = null;

    // Expose show/hide dialog state to parent
    export let showHideUserDialog = false;
    export let hideUserReason = '';
    export let flagUserForReview = false;

    // Menu state
    let isMenuOpen = false;
    let menuElement: HTMLElement;

    // Action states
    let isHiding = false;
    let hideMessage = '';
    let hideError = false;
    let isFlagging = false;
    let flagMessage = '';
    let flagError = false;
    let isFlagged = false;

    // Rating functionality state
    let userRating: 'thumbs_up' | 'thumbs_down' | null = null;
    let ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
    let isRating = false;

    // Helper function to get photo source
    function getPhotoSource(photo: PhotoData | null): string {
        if (!photo) return '';
        return photo.source?.id === 'mapillary' ? 'mapillary' : 'hillview';
    }

    $: isAuthenticated = $auth.isAuthenticated;

    // User helper functions
    function getUserId(photo: PhotoData | null): string | null {
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

    function getUserName(photo: PhotoData | null): string | null {
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

    // Hide photo function
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
            hideError = true;
            setTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, 5000);
        } finally {
            isHiding = false;
        }
        closeMenu();
    }

    // Show user hide dialog
    function showUserHideDialogAction() {
        if (!photo || !isAuthenticated) return;

        showHideUserDialog = true;
        hideUserReason = '';
        flagUserForReview = false;
        closeMenu();
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
            hideError = true;
            setTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, 3000);
        } finally {
            isRating = false;
        }
        closeMenu();
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
                    /*hideMessage = 'Shared successfully!';
                    setTimeout(() => hideMessage = '', 2000);*/
                } else {
                    throw new Error(result.error || 'Share failed');
                }
            } else {
                // Web fallback - copy to clipboard
                if (navigator.clipboard) {
                    const fullShareText = `${shareText}\n${shareUrl}`;
                    await navigator.clipboard.writeText(fullShareText);
                    hideMessage = 'Share link copied to clipboard!';
                    setTimeout(() => hideMessage = '', 4000);
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
            hideError = true;
            setTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, 3000);
        }
        closeMenu();
    }

    // Flag photo function
    async function flagPhoto() {
        if (!photo || !isAuthenticated || isFlagging) return;

        isFlagging = true;
        flagMessage = '';

        try {
            const photoSource = getPhotoSource(photo);
            const response = await http.post('/flagged/photos', {
                photo_source: photoSource,
                photo_id: photo.id,
                reason: 'Flagged for moderation'
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                if (errorData.already_flagged) {
                    flagMessage = 'Photo already flagged';
                    isFlagged = true;
                } else {
                    throw new Error(`Failed to flag photo: ${response.status}`);
                }
            } else {
                const data = await response.json();
                if (data.already_flagged) {
                    flagMessage = 'Photo already flagged';
                } else {
                    flagMessage = 'Photo flagged for moderation';
                }
                isFlagged = true;
            }

            setTimeout(() => flagMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error flagging photo:', error);
            flagMessage = `Error: ${handleApiError(error)}`;
            flagError = true;
            setTimeout(() => {
                flagMessage = '';
                flagError = false;
            }, 5000);
        } finally {
            isFlagging = false;
        }
        closeMenu();
    }

    // Unflag photo function
    async function unflagPhoto() {
        if (!photo || !isAuthenticated || isFlagging) return;

        isFlagging = true;
        flagMessage = '';

        try {
            const photoSource = getPhotoSource(photo);
            const response = await http.delete('/flagged/photos', {
                photo_source: photoSource,
                photo_id: photo.id
            });

            if (!response.ok) {
                throw new Error(`Failed to unflag photo: ${response.status}`);
            }

            flagMessage = 'Photo unflagged';
            isFlagged = false;
            setTimeout(() => flagMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error unflagging photo:', error);
            flagMessage = `Error: ${handleApiError(error)}`;
            flagError = true;
            setTimeout(() => {
                flagMessage = '';
                flagError = false;
            }, 5000);
        } finally {
            isFlagging = false;
        }
        closeMenu();
    }

    // Toggle flag status
    function toggleFlag() {
        if (isFlagged) {
            unflagPhoto();
        } else {
            flagPhoto();
        }
    }

    // Check if photo is flagged on component mount
    async function checkFlagStatus() {
        if (!photo || !isAuthenticated) return;

        try {
            const response = await http.get('/flagged/photos');
            if (response.ok) {
                const flaggedPhotos = await response.json();
                const photoSource = getPhotoSource(photo);
                isFlagged = flaggedPhotos.some((fp: any) =>
                    fp.photo_source === photoSource && fp.photo_id === photo.id
                );
            }
        } catch (error) {
            console.error('🢄Error checking flag status:', error);
        }
    }

    // Menu control functions
    function toggleMenu() {
        isMenuOpen = !isMenuOpen;
    }

    function closeMenu() {
        isMenuOpen = false;
    }

    // Handle menu action and close
    function handleMenuAction(action: () => void) {
        action();
        closeMenu();
    }

    // Click outside to close menu
    function handleClickOutside(event: MouseEvent) {
        if (menuElement && !menuElement.contains(event.target as Node)) {
            closeMenu();
        }
    }

    // Load rating and flag status when photo changes
    $: if (photo && isAuthenticated) {
        loadPhotoRating();
        checkFlagStatus();
    }

    // Navigate to user profile for Hillview photos
    async function viewUserProfile() {
        if (!photo) return;

        const photoSource = getPhotoSource(photo);
        const userId = getUserId(photo);

        if (photoSource === 'hillview' && userId) {
            myGoto(constructUserProfileUrl(userId));
        }
        else if (photoSource === 'mapillary' && (photo as any).creator?.username) {
            const username = (photo as any).creator.username;
            const profileUrl = `https://www.mapillary.com/app/user/${username}`;
            await openExternalUrl(profileUrl);
        }
    }

    // Bind click outside handler
    $: if (isMenuOpen && typeof window !== 'undefined') {
        setTimeout(() => window.addEventListener('click', handleClickOutside), 0);
    } else if (typeof window !== 'undefined') {
        window.removeEventListener('click', handleClickOutside);
    }
</script>

{#if photo}
    <div class="photo-actions-menu" bind:this={menuElement}>
        <!-- Rating buttons -->
        <button
            class="action-button rating-button {userRating === 'thumbs_up' ? 'active' : ''}"
            on:click={() => handleRatingClick('thumbs_up')}
            disabled={!isAuthenticated || isRating}
            title={!isAuthenticated ? "Sign in to rate photos" : "Thumbs up"}
            data-testid="thumbs-up-button"
        >
            <ThumbsUp size={16} />
            <span class="rating-count">{ratingCounts.thumbs_up}</span>
        </button>

        <button
            class="action-button rating-button {userRating === 'thumbs_down' ? 'active' : ''}"
            on:click={() => handleRatingClick('thumbs_down')}
            disabled={!isAuthenticated || isRating}
            title={!isAuthenticated ? "Sign in to rate photos" : "Thumbs down"}
            data-testid="thumbs-down-button"
        >
            <ThumbsDown size={16} />
            <span class="rating-count">{ratingCounts.thumbs_down}</span>
        </button>

        <!-- Menu trigger button -->
        <button
            class="menu-trigger"
            on:click={toggleMenu}
            title="More actions"
            data-testid="photo-actions-menu"
        >
            <MoreVertical size={20} />
        </button>

        <!-- Dropdown menu -->
        {#if isMenuOpen}
            <div class="menu-dropdown">
                <!-- User info section -->
                {#if getUserName(photo)}
                    <div class="menu-section">
                        <button
                            class="menu-item user-item"
                            on:click={() => handleMenuAction(viewUserProfile)}
                            data-testid="menu-user-profile"
                            title="View user profile"
                        >
                            <div class="user-info">
                                <span class="user-name">@{getUserName(photo)}</span>
                                <span class="user-source">{getPhotoSource(photo)}</span>
                            </div>
                        </button>
                    </div>
                    <div class="menu-divider"></div>
                {/if}

                <!-- Actions section -->
                <div class="menu-section">
                    <button
                        class="menu-item"
                        on:click={() => handleMenuAction(sharePhoto)}
                        data-testid="menu-share"
                        title="Share photo"
                    >
                        <Share size={16} />
                        <span>Share Photo</span>
                    </button>

                    <button
                        class="menu-item flag-item {isFlagged ? 'flagged' : ''}"
                        on:click={() => handleMenuAction(toggleFlag)}
                        disabled={!isAuthenticated || isFlagging}
                        data-testid="menu-flag"
                        title={!isAuthenticated ? "Sign in to flag photos" : (isFlagged ? "Remove flag" : "Flag for review")}
                    >
                        <Flag size={16} />
                        <span>{isFlagged ? 'Remove Flag' : 'Flag for Review'}</span>
                    </button>
                </div>

                <div class="menu-divider"></div>

                <!-- Hide section -->
                <div class="menu-section">
                    <button
                        class="menu-item hide-item"
                        on:click={() => handleMenuAction(hidePhoto)}
                        disabled={!isAuthenticated || isHiding}
                        data-testid="menu-hide-photo"
                        title={!isAuthenticated ? "Sign in to hide photos" : "Hide this photo"}
                    >
                        <EyeOff size={16} />
                        <span>Hide Photo</span>
                    </button>

                    <button
                        class="menu-item hide-item"
                        on:click={() => handleMenuAction(showUserHideDialogAction)}
                        disabled={!isAuthenticated || isHiding || !getUserId(photo)}
                        data-testid="menu-hide-user"
                        title={!isAuthenticated ? "Sign in to hide users" : `Hide all photos by ${getUserName(photo) || 'this user'}`}
                    >
                        <UserX size={16} />
                        <span>Hide User</span>
                    </button>
                </div>
            </div>
        {/if}

        <!-- Status messages -->
        {#if flagMessage || hideMessage}
            <div class="status-message" class:error={flagError || hideError}>
                {flagMessage || hideMessage}
            </div>
        {/if}
    </div>
{/if}

<style>
    .photo-actions-menu {
        position: relative;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .action-button {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: 0px 6px;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        background: white;
        color: #fff;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 12px;
        min-height: 40px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        font-weight: 500;
    }

    .action-button:hover:not(:disabled) {
        background: #f3f4f6;
        color: #111827;
    }

    .action-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    /* Rating buttons */
    .rating-button {
        background: rgba(108, 117, 125, 0.8);
    }

    .rating-button:hover:not(:disabled) {
        background: rgba(108, 117, 125, 1);
    }

    .rating-button.active {
        background: rgba(40, 167, 69, 0.8);
        color: white;
    }

    .rating-button.active:hover:not(:disabled) {
        background: rgba(40, 167, 69, 1);
    }

    .rating-count {
        font-size: 11px;
        font-weight: 600;
    }

    .menu-trigger {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        border: 1px solid #e5e7eb;
        border-radius: 26px;
        background: white;
        color: #000;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .menu-trigger:hover {
        background: #f3f4f6;
        color: #111827;
    }

    .menu-dropdown {
        position: absolute;
        bottom: 100%;
        right: 0;
        min-width: 200px;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        z-index: 1000;
        margin-bottom: 4px;
        padding: 8px 0;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }

    .menu-section {
        padding: 0 8px;
    }


    .menu-item {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        padding: 10px 12px;
        border: none;
        background: transparent;
        color: #1f2937;
        cursor: pointer;
        transition: background-color 0.2s ease, color 0.2s ease;
        text-align: left;
        border-radius: 4px;
        margin: 2px 0;
        font-weight: 600;
    }

    .menu-item:hover:not(:disabled) {
        background: #f3f4f6;
        color: #111827;
    }

    .menu-item:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .menu-divider {
        height: 1px;
        background: rgba(255, 255, 255, 0.1);
        margin: 8px 0;
    }


    .rating-count {
        margin-left: auto;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.7);
    }

    /* Flag item */
    .flag-item {
        color: #000001;
    }

    .flag-item.flagged {
        color: #000000;
    }

    /* Hide items */
    .hide-item {
        color: #0c0000;
    }

    /* Status message */
    .status-message {
        position: absolute;
        bottom: 60px;
        right: 0;
        background: rgba(40, 167, 69, 0.9);
        color: white;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        z-index: 10;
        white-space: nowrap;
        animation: fadeIn 0.3s ease;
    }

    .status-message.error {
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

    /* User info in menu */
    .user-item {
        padding: 8px 12px !important;
    }

    .user-info {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 2px;
        width: 100%;
    }

    .user-name {
        font-weight: 600;
        color: #1f2937;
        font-size: 14px;
    }

    .user-source {
        color: #6b7280;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 500;
    }

    .user-item:hover .user-name {
        color: #111827;
    }

    .user-item:hover .user-source {
        color: #4b5563;
    }

    /* Mobile responsive */
    @media (max-width: 600px) {
        .menu-dropdown {
            right: -8px;
            min-width: 180px;
        }

        .menu-item {
            padding: 8px 10px;
            font-size: 14px;
        }
    }
</style>
