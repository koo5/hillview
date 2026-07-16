<script lang="ts">
	import { onDestroy } from 'svelte';
	import { EyeOff, UserX, ThumbsUp, ThumbsDown, Share, Flag, MoreVertical, Clock, Copyright, CreativeCommons, Trash2 } from 'lucide-svelte';
	import { auth } from '$lib/auth.svelte.js';
	import DeletePhotoDialog from './DeletePhotoDialog.svelte';
	import FlagReasonDialog from './FlagReasonDialog.svelte';
	import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
	import { track } from '$lib/analytics';
	import { requireAuth } from './signInModal.svelte';
	import type { PhotoData } from '$lib/sources';
	import {
		getUserId,
		getUserName,
		getPhotoSource,
		formatCapturedAt,
		getCanonicalPhotoUrl,
		getLicenseLabel,
		getLicenseId,
		getLicenseUrl,
		getUserProfileUrl
	} from '$lib/photoUtils';
	import { openExternalUrl, HILLVIEW_BASE_URL } from '$lib/urlUtils';
	import { PHOTO_DETAIL_FETCH_DEBOUNCE_MS } from '$lib/config';
	import { TAURI } from '$lib/tauri';
	import { navigateWithHistory } from '$lib/navigation.svelte';
	import {
		hidePhotoRequest,
		togglePhotoRating,
		fetchPhotoRating,
		unflagPhotoRequest,
		fetchIsFlagged,
		viewPhotoUserProfile,
		openPhotoDetailPage,
		ratingShortcutFor,
		type Rating,
		type RatingState
	} from '$lib/photoActions';
	import { zoomViewData } from '$lib/zoomView.svelte';
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

	function cancelTimeout(id: ReturnType<typeof setTimeout> | null) {
		if (id === null) return;
		clearTimeout(id);
		pendingTimeouts.delete(id);
	}

	onDestroy(() => {
		for (const id of pendingTimeouts) {
			clearTimeout(id);
		}
		pendingTimeouts.clear();
	});

	// Expose show/hide dialog state to parent
	export let showHideUserDialog = false;

	// Admin/moderator photo deletion. The dialog is self-contained (rendered
	// below) so this works in every place the menu is mounted.
	let showDeletePhotoDialog = false;
	// Flag-with-reason dialog (shared component, rendered below).
	let showFlagDialog = false;
	// role is exposed on the user profile via /auth/me (UserOut.role).
	$: isModerator = ['admin', 'moderator'].includes(($auth.user?.role as string) ?? '');
	// Deletion only applies to our own backend's photos.
	$: canDeletePhoto = isModerator && !!photo && getPhotoSource(photo) === 'hillview';

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
	// Transient toast for dislike changes — the dislike control lives in the
	// (closed) menu, so a keyboard '-' would otherwise give no visible signal.
	let ratingMessage = '';
	let ratingMessageTimeout: ReturnType<typeof setTimeout> | null = null;

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

	// Open the admin/moderator delete-photo confirmation dialog.
	function showDeletePhotoDialogAction() {
		if (!photo || !canDeletePhoto) return;
		if (!requireAuthOrCloseMenu()) return;

		showDeletePhotoDialog = true;
		closeMenu();
	}


	// Share photo functionality
	async function sharePhoto() {
		track('share');
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

	function showRatingFeedback(message: string) {
		cancelTimeout(ratingMessageTimeout);
		ratingMessage = message;
		ratingMessageTimeout = scheduleTimeout(() => {
			ratingMessageTimeout = null;
			ratingMessage = '';
		}, 2000);
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
			// The front thumbs-up button shows its own state; the dislike sits in
			// the closed menu, so confirm dislike set/unset with a toast.
			if (rating === 'thumbs_down') {
				showRatingFeedback(
					state.userRating === 'thumbs_down' ? 'Disliked' : 'Dislike removed'
				);
			}
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

	// Keyboard shortcuts: '*' to like, '&' to dislike the front photo.
	// Skipped while the deep-zoom viewer is open so it keeps those keys.
	function handleRatingKeydown(e: KeyboardEvent) {
		if (!photo || $zoomViewData) return;
		const rating = ratingShortcutFor(e);
		if (!rating) return;
		e.preventDefault();
		handleRatingClick(rating);
	}

	// Flagging opens the reason dialog (shared component); it performs the request
	// and flips isFlagged via onFlagged.
	function openFlagDialog() {
		if (!photo || isFlagging) return;
		if (!requireAuthOrCloseMenu()) return;
		showFlagDialog = true;
		closeMenu();
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

	async function openLicenseInfo() {
		closeMenu();
		const externalUrl = photo ? getLicenseUrl(photo) : null;
		if (externalUrl) {
			await openExternalUrl(externalUrl);
			return;
		}
		if (TAURI) {
			await openExternalUrl(`${HILLVIEW_BASE_URL}/licensing`);
		} else {
			navigateWithHistory('/licensing', { reason: 'license-menu' });
		}
	}

	let ratingFetchTimeout: ReturnType<typeof setTimeout> | null = null;
	let flagFetchTimeout: ReturnType<typeof setTimeout> | null = null;

	function scheduleLoadPhotoRating() {
		cancelTimeout(ratingFetchTimeout);
		ratingFetchTimeout = null;

		if (!photo) {
			userRating = null;
			ratingCounts = { thumbs_up: 0, thumbs_down: 0 };
			return;
		}

		const target = photo;
		ratingFetchTimeout = scheduleTimeout(async () => {
			ratingFetchTimeout = null;
			if (photo !== target) return;
			const state: RatingState = await fetchPhotoRating(target);
			if (photo !== target) return;
			userRating = state.userRating;
			ratingCounts = state.ratingCounts;
		}, PHOTO_DETAIL_FETCH_DEBOUNCE_MS);
	}

	function scheduleCheckFlagStatus() {
		cancelTimeout(flagFetchTimeout);
		flagFetchTimeout = null;

		if (!photo || !is_authenticated) return;

		const target = photo;
		flagFetchTimeout = scheduleTimeout(async () => {
			flagFetchTimeout = null;
			if (photo !== target) return;
			const flagged = await fetchIsFlagged(target);
			if (photo !== target) return;
			isFlagged = flagged;
		}, PHOTO_DETAIL_FETCH_DEBOUNCE_MS);
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
				url: getUserProfileUrl(photo),
				testId: 'menu-user-profile'
			});
			items.push({ type: 'divider' });
		}

		const licenseLabel = getLicenseLabel(photo) ?? 'unknown';

		const licenseId = getLicenseId(photo);
		const externalLicenseUrl = getLicenseUrl(photo);
		// CC variants come in both lowercase (Hillview ids) and uppercase (SPDX ids).
		const isCC = !!licenseId && /^cc/i.test(licenseId);
		items.push({
			id: 'license',
			label: licenseLabel,
			icon: isCC ? CreativeCommons : Copyright,
			onclick: openLicenseInfo,
			url: externalLicenseUrl ?? '/licensing',
			testId: 'menu-license'
		});


		//if (capturedAt)
		{
			const detailUrl = getCanonicalPhotoUrl(photo);
			items.push({
				id: 'captured-at',
				label: capturedAt ?? 'unknown',
				icon: Clock,
				disabled: !detailUrl,
				onclick: openPhotoDetail,
				url: detailUrl ?? undefined,
				testId: 'menu-captured-at'
			});
		}

		items.push({
			id: 'share',
			label: 'Share Photo',
			icon: Share,
			onclick: sharePhoto,
			testId: 'menu-share'
		});
		items.push({ type: 'divider' });
		items.push({
			id: 'flag',
			label: isFlagged ? 'Remove Flag' : 'Flag for Review',
			icon: Flag,
			disabled: isFlagging,
			onclick: isFlagged ? unflagPhoto : openFlagDialog,
			testId: 'menu-flag'
		});
		items.push({
			id: 'hide-user',
			label: 'Hide User',
			icon: UserX,
			disabled: isHiding || !getUserId(photo),
			onclick: showUserHideDialogAction,
			testId: 'menu-hide-user'
		});
		items.push({
			id: 'hide-photo',
			label: 'Hide Photo',
			icon: EyeOff,
			disabled: isHiding,
			onclick: hidePhoto,
			testId: 'menu-hide-photo'
		});
		items.push({
			id: 'thumbs-down',
			label: `Dislike (${ratingCounts.thumbs_down})`,
			icon: ThumbsDown,
			selected: userRating === 'thumbs_down',
			disabled: isRating,
			onclick: () => handleRatingClick('thumbs_down'),
			testId: 'menu-thumbs-down'
		});

		// Admin/moderator-only: delete this photo from the backend.
		if (canDeletePhoto) {
			items.push({ type: 'divider' });
			items.push({
				id: 'delete-photo',
				label: 'Delete photo',
				icon: Trash2,
				onclick: showDeletePhotoDialogAction,
				testId: 'menu-delete-photo'
			});
		}

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

	// Load rating counts when photo changes (works for all users).
	// Debounced to suppress bursts of requests while the user swipes rapidly.
	$: {
		photo;
		scheduleLoadPhotoRating();
	}

	// Load flag status when photo changes (authenticated only). Debounced for the same reason.
	$: {
		photo;
		is_authenticated;
		scheduleCheckFlagStatus();
	}


</script>

<svelte:window on:keydown={handleRatingKeydown} />

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
		{#if flagMessage || hideMessage || ratingMessage}
			<div
				class="status-message"
				class:error={flagError || hideError}
				class:rating-toast={!!ratingMessage && !flagMessage && !hideMessage}
				data-testid="rating-toast"
			>
				{flagMessage || hideMessage || ratingMessage}
			</div>
		{/if}
	</div>

{/if}

<DeletePhotoDialog
	bind:show={showDeletePhotoDialog}
	{photo}
	onDeleted={() => {
		hideMessage = 'Photo deleted';
		hideError = false;
		scheduleTimeout(() => {
			hideMessage = '';
		}, 2500);
	}}
/>

<FlagReasonDialog
	bind:show={showFlagDialog}
	{photo}
	onFlagged={(message) => {
		isFlagged = true;
		flagMessage = message;
		flagError = false;
		scheduleTimeout(() => {
			flagMessage = '';
		}, 2500);
	}}
/>

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

/*	.rating-button.active.down {
		background: rgb(176, 10, 49);
		color: white;
	}*/


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

	/* Dislike confirmation — neutral, so it doesn't read as the "like" green. */
	.status-message.rating-toast {
		background: rgba(33, 37, 41, 0.92);
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
