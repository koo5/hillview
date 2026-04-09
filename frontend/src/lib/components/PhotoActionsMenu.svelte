<script lang="ts">
    import { onDestroy } from 'svelte';
    import { EyeOff, UserX, ThumbsUp, ThumbsDown, Share, Flag, MoreVertical, Clock } from 'lucide-svelte';
    import { auth } from '$lib/auth.svelte.js';
    import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
    import { requireAuth } from './signInModal.svelte';
    import type { PhotoData } from '$lib/sources';
    import {
        getUserId,
        getUserName,
        getPhotoSource,
        formatCapturedAt,
        getPhotoDetailUrl
    } from '$lib/photoUtils';
    import {
        hidePhotoRequest,
        togglePhotoRating,
        fetchPhotoRating,
        flagPhotoRequest,
        unflagPhotoRequest,
        fetchIsFlagged,
        viewPhotoUserProfile,
        openPhotoDetailPage,
        type Rating,
        type RatingState
    } from '$lib/photoActions';
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

    $: is_authenticated = $auth.is_authenticated;

    function requireAuthOrCloseMenu(): boolean {
        if (requireAuth()) return true;
        closeMenu();
        return false;
    }



    // Show user hide dialog
    function showUserHideDialogAction() {
        if (!photo) return;
        if (!requireAuthOrCloseMenu()) return;

        showHideUserDialog = true;
        closeMenu();
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

    // Hide photo wrapper — delegates to pure action
    async function hidePhoto() {
        if (!photo || isHiding) return;
        if (!requireAuthOrCloseMenu()) return;

        isHiding = true;
        hideMessage = '';
        try {
            const result = await hidePhotoRequest(photo);
            hideMessage = result.message;
            hideError = result.error;
            scheduleTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, result.error ? 5000 : 2000);
        } finally {
            isHiding = false;
            closeMenu();
        }
    }

    // Rating click wrapper
    async function handleRatingClick(rating: Rating) {
        if (!photo || isRating) return;
        if (!requireAuthOrCloseMenu()) return;

        isRating = true;
        try {
            const state = await togglePhotoRating(photo, rating, userRating);
            userRating = state.userRating;
            ratingCounts = state.ratingCounts;
        } catch (err) {
            console.error('🢄Error updating rating:', err);
            hideMessage = 'Rating error';
            hideError = true;
            scheduleTimeout(() => {
                hideMessage = '';
                hideError = false;
            }, 3000);
        } finally {
            isRating = false;
            closeMenu();
        }
    }

    async function flagPhoto() {
        if (!photo || isFlagging) return;
        if (!requireAuthOrCloseMenu()) return;

        isFlagging = true;
        flagMessage = '';
        try {
            const result = await flagPhotoRequest(photo);
            flagMessage = result.message;
            flagError = result.error;
            if (result.success) isFlagged = true;
            scheduleTimeout(() => {
                flagMessage = '';
                flagError = false;
            }, result.error ? 5000 : 2000);
        } finally {
            isFlagging = false;
            closeMenu();
        }
    }

    async function unflagPhoto() {
        if (!photo || isFlagging) return;
        if (!requireAuthOrCloseMenu()) return;

        isFlagging = true;
        flagMessage = '';
        try {
            const result = await unflagPhotoRequest(photo);
            flagMessage = result.message;
            flagError = result.error;
            if (result.success) isFlagged = false;
            scheduleTimeout(() => {
                flagMessage = '';
                flagError = false;
            }, result.error ? 5000 : 2000);
        } finally {
            isFlagging = false;
            closeMenu();
        }
    }

    function toggleFlag() {
        if (isFlagged) unflagPhoto();
        else flagPhoto();
    }

    async function viewUserProfile() {
        if (!photo) return;
        closeMenu();
        await viewPhotoUserProfile(photo);
    }

    function openPhotoDetail() {
        if (!photo) return;
        closeMenu();
        openPhotoDetailPage(photo);
    }

    async function loadPhotoRating() {
        if (!photo) {
            userRating = null;
            ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
            return;
        }
        const state: RatingState = await fetchPhotoRating(photo);
        userRating = state.userRating;
        ratingCounts = state.ratingCounts;
    }

    async function checkFlagStatus() {
        if (!photo || !is_authenticated) return;
        isFlagged = await fetchIsFlagged(photo);
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
                description: getPhotoSource(photo) ?? undefined,
                onclick: viewUserProfile,
                testId: 'menu-user-profile'
            });
            items.push({ type: 'divider' });
        }

        //if (capturedAt)
		{
            const detailUrl = getPhotoDetailUrl(photo);
            items.push({
                id: 'captured-at',
                label: capturedAt ?? 'unknown',
                icon: Clock,
                disabled: !detailUrl,
                onclick: openPhotoDetail,
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


</style>
