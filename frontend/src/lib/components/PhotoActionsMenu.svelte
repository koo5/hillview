<script lang="ts">
    import { onDestroy } from 'svelte';
    import { EyeOff, UserX, ThumbsUp, ThumbsDown, Share, Flag, MoreVertical, Clock } from 'lucide-svelte';
    import { http, handleApiError } from '$lib/http';
    import { auth } from '$lib/auth.svelte.js';
    import { simplePhotoWorker } from '$lib/simplePhotoWorker';
    import { constructUserProfileUrl, openExternalUrl } from '$lib/urlUtils';
    import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
    import { myGoto } from '$lib/navigation.svelte.js';
    import { navigateWithHistory } from '$lib/navigation.svelte.js';
    import Modal from './Modal.svelte';
    import type { PhotoData } from '$lib/sources';
	import {getPhotoSource} from "$lib/photoUtils";
    import {
        showDropdownMenu,
        closeDropdownMenu,
        dropdownMenuState,
        type DropdownMenuItem
    } from '$lib/components/dropdown-menu/dropdownMenu.svelte';

    export let photo: PhotoData | null = null;

    // Track pending timeouts for cleanup
    const pendingTimeouts = new Set<ReturnType<typeof setTimeout>>();

    function scheduleTimeout(callback: () => void, delay: number): ReturnType<typeof setTimeout> {
        const id = setTimeout(() => {
            pendingTimeouts.delete(id);
            callback();
        }, delay);
        pendingTimeouts.add(id);
        return id;
    }

    onDestroy(() => {
        for (const id of pendingTimeouts) {
            clearTimeout(id);
        }
        pendingTimeouts.clear();
    });

    // Expose show/hide dialog state to parent
    export let showHideUserDialog = false;

    // Menu state
    let menuTriggerButton: HTMLButtonElement;
    const MENU_TEST_ID = 'photo-actions-dropdown';

    $: isMenuOpen = $dropdownMenuState.visible && $dropdownMenuState.testId === MENU_TEST_ID;

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

    // Sign-in prompt modal
    let showSignInModal = false;

    $: is_authenticated = $auth.is_authenticated;

    /** Returns true if authenticated, otherwise shows sign-in modal. */
    function requireAuth(): boolean {
        if (is_authenticated) return true;
        showSignInModal = true;
        closeMenu();
        return false;
    }

    function goToLogin() {
        showSignInModal = false;
        navigateWithHistory('/login');
    }

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

    function formatCapturedAt(photo: PhotoData | null): string | null {
        if (!photo?.captured_at) return null;
        try {
            const date = new Date(photo.captured_at);
            return date.toLocaleString();
        } catch {
            return String(photo.captured_at);
        }
    }

    // Hide photo function
    async function hidePhoto() {
        if (!photo || isHiding) return;
        if (!requireAuth()) return;

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
            if (photoSource) {
                simplePhotoWorker.removePhotoFromCache?.(photo.id, photoSource);
            }

            hideMessage = 'Photo hidden successfully';
            scheduleTimeout(() => hideMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error hiding photo:', error);
            hideMessage = `Error: ${handleApiError(error)}`;
            hideError = true;
            scheduleTimeout(() => {
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
        if (!photo) return;
        if (!requireAuth()) return;

        showHideUserDialog = true;
        closeMenu();
    }

    // Rating functionality
    async function handleRatingClick(rating: 'thumbs_up' | 'thumbs_down') {
        if (!photo || isRating) return;
        if (!requireAuth()) return;

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
            scheduleTimeout(() => {
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
        if (!photo) {
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

        const result = await sharePhotoUtil(photo);
        if (result.message) {
            hideMessage = result.message;
            hideError = result.error;
            scheduleTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, result.error ? 3000 : 4000);
        }
        closeMenu();
    }

    // Flag photo function
    async function flagPhoto() {
        if (!photo || isFlagging) return;
        if (!requireAuth()) return;

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

            scheduleTimeout(() => flagMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error flagging photo:', error);
            flagMessage = `Error: ${handleApiError(error)}`;
            flagError = true;
            scheduleTimeout(() => {
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
        if (!photo || isFlagging) return;
        if (!requireAuth()) return;

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
            scheduleTimeout(() => flagMessage = '', 2000);
        } catch (error) {
            console.error('🢄Error unflagging photo:', error);
            flagMessage = `Error: ${handleApiError(error)}`;
            flagError = true;
            scheduleTimeout(() => {
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
        if (!photo || !is_authenticated) return;

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

    // Build the dropdown menu items from the current photo / action state.
    function buildItems(): DropdownMenuItem[] {
        if (!photo) return [];

        const items: DropdownMenuItem[] = [];
        const userName = getUserName(photo);
        const capturedAt = formatCapturedAt(photo);

        if (userName) {
            items.push({
                id: 'user-profile',
                label: `@${userName}`,
                description: getPhotoSource(photo),
                onclick: viewUserProfile,
                testId: 'menu-user-profile'
            });
            items.push({ type: 'divider' });
        }

        if (capturedAt) {
            items.push({
                id: 'captured-at',
                label: capturedAt,
                icon: Clock,
                onclick: () => {},
                testId: 'menu-captured-at'
            });
            items.push({ type: 'divider' });
        }

        items.push({
            id: 'share',
            label: 'Share Photo',
            icon: Share,
            onclick: sharePhoto,
            testId: 'menu-share'
        });
        items.push({
            id: 'flag',
            label: isFlagged ? 'Remove Flag' : 'Flag for Review',
            icon: Flag,
            disabled: isFlagging,
            onclick: toggleFlag,
            testId: 'menu-flag'
        });
        items.push({ type: 'divider' });
        items.push({
            id: 'hide-photo',
            label: 'Hide Photo',
            icon: EyeOff,
            disabled: isHiding,
            onclick: hidePhoto,
            testId: 'menu-hide-photo'
        });
        items.push({
            id: 'hide-user',
            label: 'Hide User',
            icon: UserX,
            disabled: isHiding || !getUserId(photo),
            onclick: showUserHideDialogAction,
            testId: 'menu-hide-user'
        });

        return items;
    }

    function toggleMenu() {
        if (isMenuOpen) {
            closeDropdownMenu();
            return;
        }
        showDropdownMenu(buildItems(), menuTriggerButton, {
            placement: 'above-right',
            testId: MENU_TEST_ID
        });
    }

    function closeMenu() {
        closeDropdownMenu();
    }

    // Load rating counts when photo changes (works for all users)
    $: if (photo) {
        loadPhotoRating();
    }

    // Load flag status when photo changes (authenticated only)
    $: if (photo && is_authenticated) {
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

</script>

{#if photo}
    <div class="photo-actions-menu">
        <!-- Rating buttons -->
        <button
            class="action-button rating-button up {userRating === 'thumbs_up' ? 'active' : ''}"
            on:click={() => handleRatingClick('thumbs_up')}
            disabled={isRating}
            title="Thumbs up"
            data-testid="thumbs-up-button"
        >
            <ThumbsUp size={16} />
            <span class="rating-count">{ratingCounts.thumbs_up}</span>
        </button>

        <button
            class="action-button rating-button down {userRating === 'thumbs_down' ? 'active' : ''}"
            on:click={() => handleRatingClick('thumbs_down')}
            disabled={isRating}
            title="Thumbs down"
            data-testid="thumbs-down-button"
        >
            <ThumbsDown size={16} />
            <span class="rating-count">{ratingCounts.thumbs_down}</span>
        </button>

        <!-- Menu trigger button -->
        <button
            bind:this={menuTriggerButton}
            class="menu-trigger"
            on:click={toggleMenu}
            title="More actions"
            data-testid="photo-actions-menu"
        >
            <MoreVertical size={20} />
        </button>

        <!-- Status messages -->
        {#if flagMessage || hideMessage}
            <div class="status-message" class:error={flagError || hideError}>
                {flagMessage || hideMessage}
            </div>
        {/if}
    </div>

    <Modal open={showSignInModal} onclose={() => showSignInModal = false} title="Sign in required" testId="sign-in-modal">
        <p class="sign-in-message">Sign in to rate, flag, and hide photos.</p>
        <div class="sign-in-actions">
            <button class="sign-in-btn" on:click={goToLogin} data-testid="sign-in-modal-login">Sign In</button>
            <button class="sign-in-cancel-btn" on:click={() => showSignInModal = false}>Cancel</button>
        </div>
    </Modal>
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

    .rating-button.active.up {
        background: rgba(40, 167, 69, 0.8);
        color: white;
    }

    .rating-button.active.down {
        background: rgb(176, 10, 49);
        color: white;
    }


    .rating-button.active:hover:not(:disabled) {
        color: black;
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

    /* Sign-in modal */
    .sign-in-message {
        margin: 0 0 16px;
        color: #374151;
        font-size: 14px;
    }

    .sign-in-actions {
        display: flex;
        gap: 12px;
        justify-content: flex-end;
    }

    .sign-in-btn {
        padding: 8px 20px;
        border: none;
        border-radius: 6px;
        background: #2563eb;
        color: white;
        font-weight: 600;
        cursor: pointer;
        font-size: 14px;
    }

    .sign-in-btn:hover {
        background: #1d4ed8;
    }

    .sign-in-cancel-btn {
        padding: 8px 20px;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        background: white;
        color: #374151;
        font-weight: 500;
        cursor: pointer;
        font-size: 14px;
    }

    .sign-in-cancel-btn:hover {
        background: #f3f4f6;
    }

</style>
