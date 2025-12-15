<script lang="ts">
	import {onMount, onDestroy} from 'svelte';
	import PhotoActionsMenu from './PhotoActionsMenu.svelte';
	import Spinner from './Spinner.svelte';
	import {app} from '$lib/data.svelte.js';
	import {auth} from '$lib/auth.svelte.js';
	import {http, handleApiError} from '$lib/http';
	import {myGoto} from '$lib/navigation.svelte.js';
	import {constructShareUrl} from '$lib/urlUtils';
	import {getDevicePhotoUrl} from '$lib/devicePhotoHelper';
	import {simplePhotoWorker} from '$lib/simplePhotoWorker';
	import {zoomViewData} from '$lib/zoomView.svelte.js';
	import {singleTap} from '$lib/actions/singleTap';
	import {getFullPhotoInfo} from '$lib/photoUtils';
	import type {PhotoData} from '$lib/sources';

	export let photo: PhotoData | null = null;
	export let className = '';
	export let clientWidth: number | undefined = undefined;
	export let onInteraction: (() => void) | undefined = undefined;

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


	$: console.log('🢄Photo.svelte: photo changed:', JSON.stringify(photo));

	// Get current user authentication state
	$: is_authenticated = $auth.is_authenticated;

	// enable for stretched backdrop
	//$: bg_style_stretched_photo = photo.sizes?.[50] ? `background-image: url(${photo.sizes[50].url});` : ''

	$: border_style = ''//className === 'front' && photo ? 'border: 4px dotted #4a90e2;' : '';
	//console.log('🢄border_style:', border_style);

	$: if (photo || clientWidth || containerElement) updateSelectedUrl();

	// Handle selectedUrl changes with background loading
	$: if (selectedUrl !== undefined && selectedUrl !== displayedUrl) {
		handleImageChange(selectedUrl);
	}

	async function updateSelectedUrl() {

		if (clientWidth)
			clientWidth2 = clientWidth;
		else if (!clientWidth2)
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
		if (photo.is_device_photo && photo.url) {
			try {
				devicePhotoUrl = getDevicePhotoUrl(photo.url);
				selectedUrl = devicePhotoUrl;
				/*console.log('🢄Photo.svelte: Device photo URL conversion:', {
					originalUrl: photo.url,
					convertedUrl: devicePhotoUrl,
					photoId: photo.id
				});*/
				return;
			} catch (error) {
				console.error('🢄Failed to load device photo:', error);
				selectedUrl = '';
				return;
			}
		}

		if (!photo.sizes) {
			console.log('🢄Photo.svelte: No sizes, using photo.url:', photo.url);
			selectedUrl = photo.url;
			return;
		}

		console.log('🢄Photo.svelte: Processing sizes for photo:', photo.id, 'is_device_photo:', photo.is_device_photo, 'sizes:', Object.keys(photo.sizes), 'clientWidth:', clientWidth2);

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
				if (photo.is_device_photo) {
					selectedUrl = getDevicePhotoUrl(p.url);
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
		if (photo.is_device_photo && photo.sizes.full) {
			selectedUrl = getDevicePhotoUrl(photo.sizes.full.url);
			console.log('🢄Photo.svelte: Using full size for device photo:', photo.id, 'original:', photo.sizes.full.url, 'converted:', selectedUrl);
		} else {
			selectedUrl = photo.sizes.full?.url || '';
			console.log('🢄Photo.svelte: Using full size for regular photo:', {
				photoId: photo.id,
				selectedUrl: selectedUrl
			});
		}

		console.log('🢄Photo.svelte: URL flow debug:', JSON.stringify({
			photoId: photo.id,
			is_device_photo: photo.is_device_photo,
			selectedUrl: selectedUrl,
			currentDisplayedUrl: displayedUrl,
			willTriggerImageChange: selectedUrl !== displayedUrl
		}));
	}

	async function handleImageChange(newUrl: string) {
		console.log('🢄Photo.svelte: handleImageChange called:', JSON.stringify({
			newUrl: newUrl,
			currentDisplayedUrl: displayedUrl,
			willReturn: !newUrl || newUrl === displayedUrl
		}));

		// hmm..
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
				console.error('🢄Failed to preload image:', newUrl);
				isLoadingNewImage = false;
				preloadImg = null;
			};

			preloadImg.src = newUrl;

		} catch (error) {
			console.error('🢄Error preloading image:', error);
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

	function cancelHideUser() {
		showHideUserDialog = false;
		hideUserReason = '';
		flagUserForReview = false;
	}

	async function confirmHideUser() {
		if (!photo || !is_authenticated || isHiding) return;

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
				requestBody.extra_data = {flagged_for_review: true};
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

	function openZoomView(photo: PhotoData) {
		if (!photo) return;

		// Notify parent about the interaction to reset swipe state
		console.log('🢄Photo: Opening zoom view, notifying parent about interaction');
		console.log('🢄Photo: onInteraction callback:', onInteraction);
		onInteraction?.();

		const fallbackUrl = displayedUrl || selectedUrl || '';
		console.log('🢄Photo.svelte: [zoomview] Opening zoom view for photo:', JSON.stringify(photo));
		const fullPhotoInfo = getFullPhotoInfo(photo);

		console.log('🢄Photo.svelte: [zoomview] Full photo info:', JSON.stringify(fullPhotoInfo));

		zoomViewData.set({
			fallback_url: fallbackUrl,
			url: fullPhotoInfo.url,
			filename: photo.file || 'Photo',
			width: fullPhotoInfo.width,
			height: fullPhotoInfo.height
		});
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
		<b>Photo:</b>
		<pre>{JSON.stringify(photo, null, 2)}</pre>
	</div>
{/if}


<div bind:this={containerElement} class="photo-wrapper">

	{#if photo?.is_placeholder}
		<div class="placeholder-container" data-testid="placeholder-photo">
			<div class="placeholder-content">
				<Spinner />
				<div class="placeholder-text">Saving photo...</div>
			</div>
		</div>
	{/if}

	{#if photo && !photo.is_placeholder}
		<img
			src={displayedUrl}
			alt={photo.file}
			style="{bg_style_stretched_photo} {border_style}"
			fetchpriority={fetchPriority as any}
			data-testid="main-photo"
			data-photo={JSON.stringify(photo)}
			onerror={(e) => {
				// onerror is "obsolete attributes" according to MDN, but still works. Eventually, we'll replace this with the service worker.
				console.error('🢄Photo.svelte: Image load error:', JSON.stringify({
					photoId: photo?.id,
					displayedUrl: displayedUrl,
					is_device_photo: photo?.is_device_photo,
					originalUrl: photo?.url,
					errorMessage: e?.toString?.() || 'Unknown error'
				}));
			}}
			onload={() => {
				console.log('🢄Photo.svelte: Image loaded successfully:', JSON.stringify({
					photoId: photo?.id,
					displayedUrl: displayedUrl,
					is_device_photo: photo?.is_device_photo
				}));
			}}
			class="photo {className}"
			use:singleTap={() => openZoomView(photo)}
		/>

		<!-- Loading spinner overlay -->
		{#if isLoadingNewImage}
			<div class="photo-loading-overlay" data-testid="photo-loading-spinner">
				<!-- Import spinner here since we don't want to import the full Spinner component -->
				<div class="photo-spinner"></div>
			</div>
		{/if}

		<!-- Photo actions for front photo only -->
		{#if className === 'front'}
			<div class="photo-actions-container">
				<PhotoActionsMenu
					{photo}
					bind:showHideUserDialog
					bind:hideUserReason
					bind:flagUserForReview
				/>
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
			<p>This will hide all photos by
				<strong>{photo && getUserName(photo) ? `@${getUserName(photo)}` : 'this user'}</strong> from your view.
			</p>

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
					onclick={cancelHideUser}
					disabled={isHiding}
				>
					Cancel
				</button>
				<button
					class="confirm-button"
					onclick={confirmHideUser}
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
		width: 100%;
		height: 100%;
		max-width: 100%;
		max-height: 100%;
		object-fit: contain;
		background-repeat: no-repeat;
		overflow: hidden;
	}

	.photo {
		object-fit: contain;
		background-size: cover;
		-o-background-size: cover;
		max-width: 100%;
		max-height: 100%;
		width: auto;
		height: auto;
	}

	.photo-actions-container {
		position: absolute;
		bottom: 12px;
		right: 10px;
		z-index: 100000;
		display: flex;
	}


	/* Front image is centered and on top */
	.front {
		z-index: 2;
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
		0% {
			transform: rotate(0deg);
		}
		100% {
			transform: rotate(360deg);
		}
	}

	.placeholder-container {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 100%);
		border-radius: 8px;
		z-index: 5;
	}

	.placeholder-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
		opacity: 0.8;
	}

	.placeholder-text {
		font-size: 14px;
		color: #666;
		font-weight: 500;
	}

</style>
