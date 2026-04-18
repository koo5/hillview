<svelte:head>
	<title>Photo - Hillview</title>
</svelte:head>

<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		EyeOff,
		UserX,
		ThumbsUp,
		ThumbsDown,
		Share,
		Flag,
		Trash2,
		Map as MapIcon,
		MoreVertical,
		Clock
	} from 'lucide-svelte';
	import { http, handleApiError, TokenExpiredError } from '$lib/http';
	import { auth } from '$lib/auth.svelte';
	import { constructPhotoMapUrl, constructUserProfileUrl, parsePhotoUidParts } from '$lib/urlUtils';
	import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
	import { myGoto } from '$lib/navigation.svelte';
	import { TAURI } from '$lib/tauri';
	import type { PhotoData } from '$lib/sources';
	import {
		getDisplayImageUrl,
		formatDateTime,
		type PublicPhoto,
		type PhotoAnnotation
	} from '$lib/photoDisplay';
	import PhotoAnnotations from '$lib/components/PhotoAnnotations.svelte';
	import {
		hidePhotoRequest,
		togglePhotoRating,
		flagPhotoRequest,
		unflagPhotoRequest,
		fetchIsFlagged,
		type Rating
	} from '$lib/photoActions';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { requireAuth } from '$lib/components/signInModal.svelte';
	import HideUserDialog from '$lib/components/HideUserDialog.svelte';
	import AnonymizationModal from '$lib/components/anonymization-modal/AnonymizationModal.svelte';
	import DropdownMenu from '$lib/components/dropdown-menu/DropdownMenu.svelte';
	import { showDropdownMenu } from '$lib/components/dropdown-menu/dropdownMenu.svelte';
	import { getPhotoMenuItemsForServerPhoto } from '$lib/photoAnonymizationMenu';

	let photo: PublicPhoto | null = null;
	let annotations: PhotoAnnotation[] = [];
	let loading = true;
	let error = '';

	// Action states (same pattern as PhotoActionsMenu.svelte)
	let isRating = false;
	let isHiding = false;
	let isFlagging = false;
	let isFlagged = false;
	let statusMessage = '';
	let statusError = false;
	let showHideUserDialog = false;

	$: photoUid = $page.params.uid;
	$: isAuthenticated = $auth.is_authenticated;

	onMount(() => {
		if (photoUid) {
			loadPhoto();
		}
	});

	// Reload when uid changes via navigation
	$: if (photoUid) {
		loadPhoto();
	}

	function setStatus(message: string, isError = false, timeoutMs = 3000) {
		statusMessage = message;
		statusError = isError;
		if (timeoutMs > 0) {
			setTimeout(() => {
				statusMessage = '';
				statusError = false;
			}, timeoutMs);
		}
	}


	async function loadPhoto() {
		if (!photoUid) {
			error = 'Photo not found';
			loading = false;
			return;
		}
		loading = true;
		error = '';
		annotations = [];
		const parts = parsePhotoUidParts(photoUid);
		try {
			const [photoRes, annotationsRes] = await Promise.all([
				http.get(`/photos/public/${encodeURIComponent(photoUid)}`),
				parts?.id
					? http.get(`/annotations/photos/${encodeURIComponent(parts.id)}`).catch(() => null)
					: Promise.resolve(null),
			]);
			if (!photoRes.ok) {
				if (photoRes.status === 404) {
					throw new Error('Photo not found');
				}
				throw new Error(`Failed to load photo: ${photoRes.status}`);
			}
			photo = await photoRes.json();
			if (annotationsRes && annotationsRes.ok) {
				annotations = await annotationsRes.json();
			}
			if (photo && isAuthenticated) {
				checkFlagStatus();
			}
		} catch (err) {
			console.error('🢄 Error loading photo:', err);
			error = handleApiError(err);
			if (err instanceof TokenExpiredError) {
				return;
			}
		} finally {
			loading = false;
		}
	}

	// --- Rating (shared with PhotoActionsMenu.svelte via photoActions.ts) ---
	async function handleRatingClick(rating: Rating) {
		if (!photo || isRating) return;
		if (!requireAuth()) return;

		isRating = true;
		try {
			const state = await togglePhotoRating(
				photo as unknown as PhotoData,
				rating,
				photo.user_rating
			);
			photo = { ...photo, user_rating: state.userRating, rating_counts: state.ratingCounts };
		} catch (err) {
			console.error('🢄 Error updating rating:', err);
			setStatus(`Rating error: ${handleApiError(err)}`, true);
		} finally {
			isRating = false;
		}
	}

	async function sharePhoto() {
		if (!photo) return;
		const result = await sharePhotoUtil(photo);
		if (result.message) {
			setStatus(result.message, result.error, result.error ? 3000 : 4000);
		}
	}

	async function hidePhoto() {
		if (!photo || isHiding) return;
		if (!requireAuth()) return;

		isHiding = true;
		try {
			const result = await hidePhotoRequest(photo as unknown as PhotoData);
			setStatus(result.message, result.error, result.error ? 5000 : 3000);
		} finally {
			isHiding = false;
		}
	}

	async function flagPhoto() {
		if (!photo || isFlagging) return;
		if (!requireAuth()) return;

		isFlagging = true;
		try {
			const result = await flagPhotoRequest(photo as unknown as PhotoData);
			if (result.success) isFlagged = true;
			setStatus(result.message, result.error, result.error ? 5000 : 3000);
		} finally {
			isFlagging = false;
		}
	}

	async function unflagPhoto() {
		if (!photo || isFlagging) return;
		if (!requireAuth()) return;

		isFlagging = true;
		try {
			const result = await unflagPhotoRequest(photo as unknown as PhotoData);
			if (result.success) isFlagged = false;
			setStatus(result.message, result.error, result.error ? 5000 : 3000);
		} finally {
			isFlagging = false;
		}
	}

	function toggleFlag() {
		if (isFlagged) unflagPhoto();
		else flagPhoto();
	}

	async function checkFlagStatus() {
		if (!photo || !isAuthenticated) return;
		isFlagged = await fetchIsFlagged(photo as unknown as PhotoData);
	}

	// --- Delete (same pattern as /photos/+page.svelte) ---
	async function deletePhoto() {
		if (!photo) return;
		if (!confirm('Are you sure you want to delete this photo?')) return;

		try {
			const response = await http.delete(`/photos/${photo.id}`);
			if (!response.ok) {
				const errorText = await response.text();
				throw new Error(`Failed to delete photo: ${response.status} ${errorText}`);
			}
			setStatus('Photo deleted', false, 1500);
			// Navigate back to My Photos after a brief delay
			setTimeout(() => myGoto('/photos'), 1000);
		} catch (err) {
			console.error('🢄 Error deleting photo:', err);
			setStatus(`Delete failed: ${handleApiError(err)}`, true, 5000);
		}
	}

	// --- Anonymization menu (same pattern as /photos/+page.svelte) ---
	function showAnonymizationMenu(event: MouseEvent) {
		if (!photo) return;
		const button = event.currentTarget as HTMLButtonElement;
		const items = getPhotoMenuItemsForServerPhoto(photo.id);
		showDropdownMenu(items, button, {
			placement: 'below-right',
			testId: 'photo-detail-anonymization-menu'
		});
	}

	function viewUserProfile() {
		if (!photo?.owner_id) return;
		myGoto(constructUserProfileUrl(photo.owner_id));
	}

	function viewOnMap() {
		if (!photo) return;
		myGoto(constructPhotoMapUrl(photo));
	}
</script>

<StandardHeaderWithAlert
	title={photo?.description || photo?.original_filename || 'Photo'}
	showMenuButton={true}
	fallbackHref="/"
/>

{#if photo?.owner_id}
	<HideUserDialog
		bind:show={showHideUserDialog}
		userId={photo.owner_id}
		username={photo.owner_username}
		userSource="hillview"
	/>
{/if}

<StandardBody>
	{#if loading}
		<div class="loading-container" data-testid="photo-detail-loading">
			<Spinner />
			<p>Loading photo...</p>
		</div>
	{:else if error}
		<div class="error-container" data-testid="photo-detail-error">
			<p>{error}</p>
			<button class="retry-button" on:click={loadPhoto}>Try Again</button>
		</div>
	{:else if photo}
		<div class="photo-detail" data-testid="photo-detail">
			<div class="photo-container">
				<img
					src={getDisplayImageUrl(photo)}
					alt={photo.original_filename || 'Photo'}
					data-testid="photo-detail-image"
				/>
			</div>

			<div class="metadata">
				{#if photo.description}
					<p class="description" data-testid="photo-detail-description">{photo.description}</p>
				{/if}

				<div class="meta-row">
					{#if photo.owner_username}
						<button
							class="owner-link"
							on:click={viewUserProfile}
							data-testid="photo-detail-owner"
						>
							@{photo.owner_username}
						</button>
					{/if}
					{#if photo.captured_at}
						<span class="captured">
							<Clock size={14} />
							{formatDateTime(photo.captured_at)}
						</span>
					{/if}
				</div>

				{#if photo.latitude != null && photo.longitude != null}
					<div class="meta-row">
						<button
							class="map-link"
							on:click={viewOnMap}
							data-testid="photo-detail-view-on-map"
						>
							<MapIcon size={14} />
							View on Map ({photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)})
						</button>
					</div>
				{/if}

				{#if photo.uploaded_at}
					<p class="uploaded" data-testid="photo-detail-uploaded">
						Uploaded: {formatDateTime(photo.uploaded_at)}
					</p>
				{/if}
			</div>

			<!-- Rating buttons (same as PhotoActionsMenu) -->
			<div class="actions-row">
				<button
					class="action-button rating {photo.user_rating === 'thumbs_up' ? 'active up' : ''}"
					on:click={() => handleRatingClick('thumbs_up')}
					disabled={isRating}
					data-testid="thumbs-up-button"
				>
					<ThumbsUp size={16} />
					<span class="rating-count">{photo.rating_counts.thumbs_up}</span>
				</button>

				<button
					class="action-button rating {photo.user_rating === 'thumbs_down' ? 'active down' : ''}"
					on:click={() => handleRatingClick('thumbs_down')}
					disabled={isRating}
					data-testid="thumbs-down-button"
				>
					<ThumbsDown size={16} />
					<span class="rating-count">{photo.rating_counts.thumbs_down}</span>
				</button>

				<button
					class="action-button"
					on:click={sharePhoto}
					data-testid="menu-share"
					title="Share photo"
				>
					<Share size={16} />
					<span>Share</span>
				</button>

				<button
					class="action-button {isFlagged ? 'flagged' : ''}"
					on:click={toggleFlag}
					disabled={isFlagging}
					data-testid="menu-flag"
					title={isFlagged ? 'Remove flag' : 'Flag for review'}
				>
					<Flag size={16} />
					<span>{isFlagged ? 'Remove Flag' : 'Flag'}</span>
				</button>

				<button
					class="action-button"
					on:click={hidePhoto}
					disabled={isHiding}
					data-testid="menu-hide-photo"
					title="Hide this photo"
				>
					<EyeOff size={16} />
					<span>Hide</span>
				</button>

				<button
					class="action-button"
					on:click={() => requireAuth() && (showHideUserDialog = true)}
					disabled={!photo.owner_id}
					data-testid="menu-hide-user"
					title={`Hide all photos by ${photo.owner_username || 'this user'}`}
				>
					<UserX size={16} />
					<span>Hide User</span>
				</button>
			</div>

			<!-- Owner-only actions (same as /photos page) -->
			{#if photo.is_own_photo}
				<div class="owner-actions" data-testid="photo-detail-owner-actions">
					<button
						class="action-button delete"
						on:click={deletePhoto}
						data-testid="delete-photo-button"
						data-photo-id={photo.id}
					>
						<Trash2 size={16} />
						Delete
					</button>
					{#if TAURI}
						<button
							class="action-button"
							on:click={showAnonymizationMenu}
							title="Anonymization options"
							data-testid="photo-menu-button"
						>
							<MoreVertical size={16} />
							More
						</button>
					{/if}
				</div>
			{/if}

			<PhotoAnnotations {annotations} />

			{#if statusMessage}
				<div class="status-message" class:error={statusError} data-testid="photo-detail-status">
					{statusMessage}
				</div>
			{/if}
		</div>
	{/if}
</StandardBody>

<DropdownMenu />
<AnonymizationModal />

<style>
	.loading-container,
	.error-container {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		padding: 4rem 0;
	}

	.retry-button {
		padding: 0.5rem 1rem;
		background: #4a90e2;
		color: white;
		border: none;
		border-radius: 4px;
		cursor: pointer;
	}

	.photo-detail {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
	}

	.photo-container {
		display: flex;
		justify-content: center;
		margin-bottom: 20px;
		background: #f8f9fa;
		border-radius: 8px;
		overflow: hidden;
	}

	.photo-container img {
		max-width: 100%;
		max-height: 70vh;
		object-fit: contain;
	}

	.metadata {
		margin-bottom: 20px;
	}

	.description {
		font-size: 1rem;
		color: #333;
		margin: 0 0 12px 0;
	}

	.meta-row {
		display: flex;
		gap: 16px;
		align-items: center;
		flex-wrap: wrap;
		margin-bottom: 8px;
		color: #555;
		font-size: 0.9rem;
	}

	.captured {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.owner-link,
	.map-link {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		background: none;
		border: none;
		color: #1565c0;
		cursor: pointer;
		padding: 0;
		font-size: inherit;
		text-decoration: underline;
	}

	.owner-link:hover,
	.map-link:hover {
		color: #0d47a1;
	}

	.uploaded {
		font-size: 0.8rem;
		color: #888;
		margin: 4px 0 0 0;
	}

	.actions-row {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		padding-top: 16px;
		border-top: 1px solid #eee;
	}

	.owner-actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		margin-top: 16px;
		padding-top: 16px;
		border-top: 1px solid #eee;
	}

	.action-button {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		border: 1px solid #e5e7eb;
		border-radius: 4px;
		background: white;
		color: #1f2937;
		cursor: pointer;
		font-size: 14px;
		font-weight: 500;
		transition: all 0.2s ease;
	}

	.action-button:hover:not(:disabled) {
		background: #f3f4f6;
		color: #111827;
	}

	.action-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.action-button.rating.active.up {
		background: rgba(40, 167, 69, 0.85);
		color: white;
		border-color: transparent;
	}

	.action-button.rating.active.down {
		background: rgb(176, 10, 49);
		color: white;
		border-color: transparent;
	}

	.action-button.delete {
		background: #fef2f2;
		color: #b91c1c;
		border-color: #fecaca;
	}

	.action-button.delete:hover {
		background: #fee2e2;
	}

	.action-button.flagged {
		background: #fffbeb;
		color: #92400e;
		border-color: #fde68a;
	}

	.rating-count {
		font-size: 12px;
		font-weight: 600;
	}

	.status-message {
		margin-top: 16px;
		padding: 8px 12px;
		background: rgba(40, 167, 69, 0.1);
		color: #166534;
		border: 1px solid rgba(40, 167, 69, 0.3);
		border-radius: 4px;
		font-size: 14px;
	}

	.status-message.error {
		background: rgba(220, 53, 69, 0.1);
		color: #991b1b;
		border-color: rgba(220, 53, 69, 0.3);
	}

</style>
