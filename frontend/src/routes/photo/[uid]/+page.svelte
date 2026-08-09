<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
	import {
		EyeOff,
		UserX,
		ThumbsUp,
		ThumbsDown,
		Share,
		Flag,
		Trash2,
		Glasses,
		Clock,
		Pencil
	} from 'lucide-svelte';
	import { http, handleApiError, TokenExpiredError } from '$lib/http';
	import { auth } from '$lib/auth.svelte';
	import { constructPhotoMapUrl, constructUserProfileUrl, parsePhotoUidParts } from '$lib/urlUtils';
	import { sharePhoto as sharePhotoUtil } from '$lib/shareUtils';
	import { myGoto } from '$lib/navigation.svelte';
	import { TAURI, BROWSER } from '$lib/tauri';
	import type { PhotoData } from '$lib/sources';
	import {
		getDisplayImageUrl,
		formatDateTime,
		pickOgImage,
		buildPhotoImageJsonLd,
		buildHeadTitle,
		buildHeadDescription,
		buildAnnotationSummary,
		displayTitle,
		type PublicPhoto,
		type PhotoAnnotation
	} from '$lib/photoDisplay';
	import PhotoAnnotations from '$lib/components/PhotoAnnotations.svelte';
	import PhotoHead from '$lib/components/PhotoHead.svelte';
	import JsonLd from '$lib/components/JsonLd.svelte';
	import {
		hidePhotoRequest,
		togglePhotoRating,
		unflagPhotoRequest,
		fetchIsFlagged,
		ratingShortcutFor,
		type Rating
	} from '$lib/photoActions';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { requireAuth } from '$lib/components/signInModal.svelte';
	import HideUserDialog from '$lib/components/HideUserDialog.svelte';
	import FlagReasonDialog from '$lib/components/FlagReasonDialog.svelte';
	import AnonymizationModal from '$lib/components/anonymization-modal/AnonymizationModal.svelte';
	import { openAnonymizationModalForServerPhoto } from '$lib/components/anonymization-modal/anonymizationModal.svelte.js';
	import { isModerator } from '$lib/adminNotifications';

	export let data: { photo?: PublicPhoto; annotations?: PhotoAnnotation[] } | undefined = undefined;

	let photo: PublicPhoto | null = data?.photo ?? null;
	let annotations: PhotoAnnotation[] = data?.annotations ?? [];
	let loading = !data?.photo;
	let error = '';

	// Action states (same pattern as PhotoActionsMenu.svelte)
	let isRating = false;
	let isHiding = false;
	let isFlagging = false;
	let isFlagged = false;
	let showFlagDialog = false;
	let statusMessage = '';
	let statusError = false;
	let showHideUserDialog = false;

	$: photoUid = $page.params.uid;
	$: isAuthenticated = $auth.is_authenticated;

	// Load from the network whenever the route uid doesn't match the photo we have.
	// Covers both first mount without SSR data and SPA navigation to a different photo.
	$: if (photoUid && (!photo || photo.uid !== photoUid)) {
		loadPhoto();
	}

	// SSR runs unauthenticated so user-specific fields (user_rating, is_own_photo)
	// come back null/false. When we hydrated from SSR data, re-fetch once under
	// the client's auth token to pick those up, without flashing the spinner.
	onMount(() => {
		if (data?.photo) loadPhoto(true);
	});

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


	async function loadPhoto(silent = false) {
		if (!photoUid) {
			error = 'Photo not found';
			loading = false;
			return;
		}
		if (!silent) {
			loading = true;
			annotations = [];
		}
		error = '';
		try {
			const response = await http.get(`/photos/public/${encodeURIComponent(photoUid)}`);
			if (!response.ok) {
				if (response.status === 404) {
					throw new Error('Photo not found');
				}
				throw new Error(`Failed to load photo: ${response.status}`);
			}
			photo = await response.json();
			if (photo && isAuthenticated) {
				checkFlagStatus();
			}
		} catch (err) {
			console.error('🢄 Error loading photo:', err);
			if (!silent) error = handleApiError(err);
			if (err instanceof TokenExpiredError) {
				return;
			}
		} finally {
			if (!silent) loading = false;
		}

		// Annotations load independently — a failure here must not hide the photo.
		const parts = parsePhotoUidParts(photoUid);
		if (photo && parts?.id) {
			try {
				const resp = await http.get(`/annotations/photos/${encodeURIComponent(parts.id)}`);
				if (resp.ok) annotations = await resp.json();
			} catch (err) {
				console.error('🢄 Error loading annotations:', err);
			}
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

	// Keyboard shortcuts: '*' to like, '&' to dislike this photo.
	function handleRatingKeydown(e: KeyboardEvent) {
		if (!photo) return;
		const rating = ratingShortcutFor(e);
		if (!rating) return;
		e.preventDefault();
		handleRatingClick(rating);
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

	// Flagging opens the shared reason dialog (rendered below).
	function flagPhoto() {
		if (!photo || isFlagging) return;
		if (!requireAuth()) return;
		showFlagDialog = true;
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

	// --- Metadata edit form (title/description/bearing, plus mod-only featured) ---
	// Owners edit their own photo; moderators edit any. Synced from the photo only
	// when a different photo loads (guarded by uid), so in-progress edits survive
	// the reassignments rating clicks make.
	let editUid = '';
	let editTitle = '';
	let editDescription = '';
	let editBearing: number | null = null;
	let editFeatured = false;
	let isSavingEdit = false;

	$: canEditPhoto = !!photo && photo.source === 'hillview' && (photo.is_own_photo || $isModerator);

	$: if (photo && photo.uid !== editUid) {
		editUid = photo.uid;
		syncEditForm(photo);
	}

	function syncEditForm(p: PublicPhoto) {
		editTitle = p.title ?? '';
		editDescription = p.description ?? '';
		editBearing = p.bearing;
		editFeatured = p.featured ?? false;
	}

	async function saveEdit() {
		if (!photo || isSavingEdit) return;

		isSavingEdit = true;
		try {
			// featured is moderator-only; sending it as a plain owner would be
			// rejected the moment it differs from what's stored.
			const response = await http.patch(`/photos/${photo.id}`, {
				title: editTitle,
				description: editDescription,
				bearing: editBearing,
				...($isModerator ? { featured: editFeatured } : {})
			});
			if (!response.ok) {
				const errorText = await response.text();
				throw new Error(`Failed to save: ${response.status} ${errorText}`);
			}
			const updated = await response.json();
			photo = {
				...photo,
				title: updated.title,
				description: updated.description,
				featured: updated.featured,
				bearing: updated.bearing
			};
			syncEditForm(photo);
			setStatus(
				updated.changed.length ? `Saved: ${updated.changed.join(', ')}` : 'No changes to save',
				false,
				3000
			);
		} catch (err) {
			console.error('🢄 Error saving photo edit:', err);
			setStatus(`Save failed: ${handleApiError(err)}`, true, 5000);
		} finally {
			isSavingEdit = false;
		}
	}

	$: headTitle = photo ? buildHeadTitle(photo, annotations) : '';
	$: headOgImage = photo ? pickOgImage(photo) : null;
	$: headDescription = photo ? buildHeadDescription(photo, annotations) : '';
	// Visible twin of the head-description fallback: when the author wrote no
	// description, say what the annotations name right under the title. Visible
	// text is a stronger snippet source for crawlers than any meta tag — the
	// page otherwise ends in menu items.
	$: annotationSummary = photo && !photo.description ? buildAnnotationSummary(annotations) : '';
	// schema.org ImageObject for the photo (precise structured data, incl. the
	// annotated landmark labels as keywords). Built in photoDisplay so it's
	// unit-testable against real payloads.
	$: headJsonLd = buildPhotoImageJsonLd(photo, annotations);
</script>

<svelte:window on:keydown={handleRatingKeydown} />

{#if photo}
	<PhotoHead
		title={headTitle}
		description={headDescription}
		ogType="article"
		ogImage={headOgImage ? { url: headOgImage.url, width: headOgImage.width, height: headOgImage.height } : null}
		latitude={photo.latitude}
		longitude={photo.longitude}
		canonicalUrl={`${HILLVIEW_BASE_URL}/photo/${encodeURIComponent(photo.uid)}`}
	/>
	<JsonLd data={headJsonLd} />
{/if}

<StandardHeaderWithAlert
	title={photo ? displayTitle(photo, annotations) : 'Photo'}
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

	<FlagReasonDialog
		bind:show={showFlagDialog}
		photo={photo as unknown as PhotoData}
		onFlagged={(message) => {
			isFlagged = true;
			setStatus(message, false, 3000);
		}}
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
			<button class="retry-button" on:click={() => loadPhoto()}>Try Again</button>
		</div>
	{:else if photo}
		<div class="photo-detail" data-testid="photo-detail">
			{#if annotationSummary}
				<p class="annotation-summary" data-testid="photo-detail-summary">{annotationSummary}</p>
			{/if}

			<!-- The photo itself opens the interactive map/zoomview — same target
			     as the Location detail below. A real anchor, not a click handler:
			     this page is the canonical target for shared photos, so the hop to
			     the interactive map must be crawlable and open-in-new-tab-able. -->
			<a
				class="photo-container"
				href={constructPhotoMapUrl(photo)}
				title="Open in the interactive map"
				data-testid="photo-detail-image-link"
			>
				<img
					src={getDisplayImageUrl(photo)}
					alt={displayTitle(photo, annotations)}
					data-testid="photo-detail-image"
				/>
			</a>

			<div class="metadata">
				{#if photo.description}
					<p class="description" data-testid="photo-detail-description">{photo.description}</p>
				{/if}

				<!-- Every fact in one uniformly labeled row -->
				<div class="details-row" data-testid="photo-detail-details">
					{#if photo.owner_username}
						<span class="detail">
							<span class="detail-label">By</span>
							{#if photo.owner_id}
								<a href={constructUserProfileUrl(photo.owner_id)} data-testid="photo-detail-owner">@{photo.owner_username}</a>
							{:else}
								<span data-testid="photo-detail-owner">@{photo.owner_username}</span>
							{/if}
						</span>
					{/if}
					{#if photo.captured_at}
						<span class="detail">
							<span class="detail-label">Captured</span>
							<span data-testid="photo-detail-captured">{formatDateTime(photo.captured_at)}</span>
						</span>
					{/if}
					{#if photo.uploaded_at}
						<span class="detail">
							<span class="detail-label">Uploaded</span>
							<span data-testid="photo-detail-uploaded">{formatDateTime(photo.uploaded_at)}</span>
						</span>
					{/if}
					{#if photo.latitude != null && photo.longitude != null}
						<span class="detail">
							<span class="detail-label">Location</span>
							<a href={constructPhotoMapUrl(photo)} data-testid="photo-detail-view-on-map"
								>{photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}</a>
						</span>
					{/if}
				</div>
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
					{#if TAURI || BROWSER}
						<!-- Direct button — this used to be a "More" dropdown whose menu
						     held exactly this one action -->
						<button
							class="action-button"
							on:click={() => photo && openAnonymizationModalForServerPhoto(photo.id)}
							title="Change blur settings"
							data-testid="photo-detail-anonymization-button"
						>
							<Glasses size={16} />
							Anonymization
						</button>
					{/if}
				</div>
			{/if}

			<!-- Metadata edit form with an explicit save: owners edit their own
			     photo, moderators any. Featured is a curation flag, so only
			     moderators see it. Hillview photos only — external sources
			     can't be edited. -->
			{#if canEditPhoto}
				<div class="photo-edit" data-testid="photo-edit-form">
					<h3 class="photo-edit-heading">
						<Pencil size={14} />
						{photo.is_own_photo ? 'Edit details' : 'Edit details (moderator)'}
					</h3>
					<label class="edit-field">
						<span>Title</span>
						<input
							type="text"
							bind:value={editTitle}
							data-testid="photo-edit-title-input"
						/>
					</label>
					<label class="edit-field">
						<span>Description</span>
						<textarea
							rows="3"
							bind:value={editDescription}
							data-testid="photo-edit-description-input"
						></textarea>
					</label>
					<div class="edit-field-row">
						<label class="edit-field bearing">
							<span>Bearing°</span>
							<input
								type="number"
								step="any"
								placeholder="unchanged"
								bind:value={editBearing}
								data-testid="photo-edit-bearing-input"
							/>
						</label>
						{#if $isModerator}
							<label class="edit-checkbox">
								<input
									type="checkbox"
									bind:checked={editFeatured}
									data-testid="photo-edit-featured-checkbox"
								/>
								<span>Featured</span>
							</label>
						{/if}
						<button
							class="action-button save"
							on:click={saveEdit}
							disabled={isSavingEdit}
							data-testid="photo-edit-save-button"
						>
							{isSavingEdit ? 'Saving…' : 'Save'}
						</button>
					</div>
				</div>
			{/if}

			<PhotoAnnotations {annotations} {photo} />

			<!-- Moderators/admins can inspect the full edit history of this photo's annotations. -->
			{#if $isModerator && photoUid && parsePhotoUidParts(photoUid)?.source === 'hillview'}
				<a
					class="annotation-history-link"
					href={`/photo/${photoUid}/annotations`}
					data-testid="photo-annotation-history-link"
				>
					<Clock size={14} /> Annotation history
				</a>
			{/if}

			{#if statusMessage}
				<div class="status-message" class:error={statusError} data-testid="photo-detail-status">
					{statusMessage}
				</div>
			{/if}
		</div>
	{/if}
</StandardBody>

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

	.annotation-history-link {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		margin-top: 12px;
		font-size: 0.85rem;
		font-weight: 600;
		color: #4f46e5;
		text-decoration: none;
	}

	.annotation-history-link:hover {
		text-decoration: underline;
	}

	.annotation-summary {
		margin: 0 0 12px 0;
		color: #555;
		font-size: 0.95rem;
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

	.details-row {
		display: flex;
		gap: 16px;
		align-items: baseline;
		flex-wrap: wrap;
		color: #555;
		font-size: 0.9rem;
	}

	.detail-label {
		color: #999;
		margin-right: 2px;
	}

	.detail a {
		color: #1565c0;
		text-decoration: underline;
	}

	.detail a:hover {
		color: #0d47a1;
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

	.photo-edit {
		margin-top: 16px;
		padding-top: 16px;
		border-top: 1px solid #eee;
	}

	.photo-edit-heading {
		display: flex;
		align-items: center;
		gap: 6px;
		margin: 0 0 10px 0;
		font-size: 0.9rem;
		font-weight: 600;
		color: #4f46e5;
	}

	.edit-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-bottom: 10px;
		font-size: 0.85rem;
		color: #555;
	}

	.edit-field input,
	.edit-field textarea {
		padding: 6px 8px;
		border: 1px solid #d1d5db;
		border-radius: 4px;
		font-size: 14px;
		font-family: inherit;
		color: #1f2937;
	}

	.edit-field-row {
		display: flex;
		gap: 16px;
		align-items: center;
		flex-wrap: wrap;
	}

	.edit-field-row .edit-field {
		margin-bottom: 0;
	}

	.edit-field.bearing input {
		width: 110px;
	}

	.edit-checkbox {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.9rem;
		color: #555;
		cursor: pointer;
	}

	.action-button.save {
		background: #4a90e2;
		color: white;
		border-color: transparent;
	}

	.action-button.save:hover:not(:disabled) {
		background: #3b7fd1;
		color: white;
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
