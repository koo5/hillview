<script lang="ts">
	import Modal from '../Modal.svelte';
	import { Glasses, Smile, AlertCircle, Loader2, Check } from 'lucide-svelte';
	import { createAnonymizationEdit, getDevicePhotoIdByServerPhotoId, checkPhotoFileExists, getPhotoAnonymizationState, triggerUploadLoop, type AnonymizationState } from '$lib/photoAnonymizationMenu';
	import { addAlert } from '$lib/alertSystem.svelte';
	import { anonymizationModalState, closeAnonymizationModal } from './anonymizationModal.svelte.js';
	import { BROWSER } from '$lib/tauri';

	type ModalState =
		| { status: 'loading' }
		| { status: 'not-found-locally' }
		| { status: 'file-missing'; path: string }
		| { status: 'browser-not-supported' }
		| { status: 'ready'; devicePhotoId: string; currentState: AnonymizationState }
		| { status: 'processing'; currentState: AnonymizationState };

	let modalState: ModalState = $state({ status: 'loading' });

	// When modal opens, check if photo is available
	$effect(() => {
		if ($anonymizationModalState.visible) {
			checkPhotoAvailability();
		} else {
			// Reset state when modal closes
			modalState = { status: 'loading' };
		}
	});

	async function checkPhotoAvailability() {
		const { photoId, isServerPhoto } = $anonymizationModalState;
		if (!photoId) return;

		modalState = { status: 'loading' };

		// In browser mode, we can't access local device photos
		if (BROWSER) {
			modalState = { status: 'browser-not-supported' };
			return;
		}

		try {
			let devicePhotoId: string;

			// Step 1: For server photos, look up the device photo ID
			if (isServerPhoto) {
				const lookupResult = await getDevicePhotoIdByServerPhotoId(photoId);
				if (!lookupResult) {
					modalState = { status: 'not-found-locally' };
					return;
				}
				devicePhotoId = lookupResult;
			} else {
				devicePhotoId = photoId as string;
			}

			// Step 2: Check if the actual file exists
			const fileCheck = await checkPhotoFileExists(devicePhotoId);
			if (!fileCheck.success) {
				modalState = { status: 'file-missing', path: fileCheck.path || 'unknown' };
				return;
			}
			if (!fileCheck.exists) {
				modalState = { status: 'file-missing', path: fileCheck.path || 'unknown' };
				return;
			}

			// Step 3: Get current anonymization state
			const stateResult = await getPhotoAnonymizationState(devicePhotoId);
			const currentState: AnonymizationState = stateResult.success && stateResult.state ? stateResult.state : 'auto';

			// All good - show options
			modalState = { status: 'ready', devicePhotoId, currentState };

		} catch (err) {
			console.error('Error checking photo availability:', err);
			modalState = { status: 'file-missing', path: 'unknown' };
		}
	}

	async function handleOption(value: null | any[], label: string, newState: AnonymizationState) {
		if (modalState.status !== 'ready') return;

		const { devicePhotoId, currentState } = modalState;

		// Don't do anything if selecting the same option
		if (newState === currentState) {
			closeAnonymizationModal();
			return;
		}

		modalState = { status: 'processing', currentState };

		try {
			const result = await createAnonymizationEdit(devicePhotoId, value);
			if (result.success && result.edit_id) {
				addAlert(`${label} - queued for re-upload`, 'success', {
					duration: 3000,
					source: 'anonymization-edit'
				});
				// Trigger upload loop to process the edit
				triggerUploadLoop();
			} else {
				addAlert(`Failed: ${result.error || 'Unknown error'}`, 'error', {
					duration: 5000,
					source: 'anonymization-edit'
				});
			}
		} finally {
			closeAnonymizationModal();
		}
	}
</script>

<Modal
	open={$anonymizationModalState.visible}
	onclose={closeAnonymizationModal}
	title="Anonymization Options"
	testId="anonymization-modal"
>
	{#if modalState.status === 'loading'}
		<div class="state-message">
			<div class="state-icon loading">
				<Loader2 size={32} />
			</div>
			<p>Checking photo availability...</p>
		</div>

	{:else if modalState.status === 'browser-not-supported'}
		<div class="state-message">
			<div class="state-icon warning">
				<AlertCircle size={32} />
			</div>
			<h4>Not available in browser</h4>
			<p>
				Changing anonymization settings is only available in the mobile app.
				Please use the Hillview app on your device to modify these settings.
			</p>
		</div>

	{:else if modalState.status === 'not-found-locally'}
		<div class="state-message">
			<div class="state-icon warning">
				<AlertCircle size={32} />
			</div>
			<h4>Photo not found on device</h4>
			<p>
				This photo was uploaded from a different device or is no longer in the local database.
				Anonymization settings can only be changed from the device that originally captured the photo.
			</p>
		</div>

	{:else if modalState.status === 'file-missing'}
		<div class="state-message">
			<div class="state-icon warning">
				<AlertCircle size={32} />
			</div>
			<h4>Photo file not found</h4>
			<p>
				The original photo file is no longer available on this device.
				It may have been deleted or moved.
			</p>
			<p class="file-path">
				Expected location: {modalState.path}
			</p>
		</div>

	{:else if modalState.status === 'ready' || modalState.status === 'processing'}
		{@const currentState = modalState.currentState}
		<div class="options-list">
			<button
				class="option-button"
				class:selected={currentState === 'auto'}
				onclick={() => handleOption(null, 'Auto-detect & blur', 'auto')}
				disabled={modalState.status === 'processing'}
				data-testid="option-auto-anonymize"
			>
				<span class="radio-indicator" class:checked={currentState === 'auto'}>
					{#if currentState === 'auto'}
						<Check size={14} />
					{/if}
				</span>
				<span class="option-icon">
					<Glasses size={24} />
				</span>
				<span class="option-content">
					<span class="option-label">Auto-detect & blur</span>
					<span class="option-description">Automatically detect and blur faces and license plates</span>
				</span>
			</button>

			<button
				class="option-button"
				class:selected={currentState === 'none'}
				onclick={() => handleOption([], 'No anonymization', 'none')}
				disabled={modalState.status === 'processing'}
				data-testid="option-skip-anonymization"
			>
				<span class="radio-indicator" class:checked={currentState === 'none'}>
					{#if currentState === 'none'}
						<Check size={14} />
					{/if}
				</span>
				<span class="option-icon">
					<Smile size={24} />
				</span>
				<span class="option-content">
					<span class="option-label">No anonymization</span>
					<span class="option-description">Upload the photo without any blurring</span>
				</span>
			</button>
		</div>

		<p class="help-text">
			{#if currentState === 'auto'}
				Currently set to auto-detect. Select a different option to change.
			{:else if currentState === 'none'}
				Currently set to no anonymization. Select a different option to change.
			{:else}
				Currently using custom blur regions.
			{/if}
		</p>
	{/if}
</Modal>

<style>
	.state-message {
		text-align: center;
		padding: 20px 0;
	}

	.state-message h4 {
		margin: 16px 0 8px;
		color: #1f2937;
		font-size: 16px;
	}

	.state-message p {
		margin: 0 0 8px;
		color: #6b7280;
		font-size: 14px;
		line-height: 1.5;
	}

	.state-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 64px;
		height: 64px;
		margin: 0 auto;
		border-radius: 50%;
	}

	.state-icon.loading {
		color: #3b82f6;
		animation: spin 1s linear infinite;
	}

	.state-icon.warning {
		background: #fef3c7;
		color: #d97706;
	}

	.file-path {
		font-family: monospace;
		font-size: 12px;
		background: #f3f4f6;
		padding: 8px 12px;
		border-radius: 6px;
		word-break: break-all;
		margin-top: 12px;
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}

	.options-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.option-button {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		width: 100%;
		padding: 14px;
		border: 2px solid #e5e7eb;
		border-radius: 10px;
		background: white;
		cursor: pointer;
		text-align: left;
		transition: all 0.15s ease;
	}

	.option-button:hover:not(:disabled) {
		border-color: #3b82f6;
		background: #f8fafc;
	}

	.option-button.selected {
		border-color: #3b82f6;
		background: #eff6ff;
	}

	.option-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.radio-indicator {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		border: 2px solid #d1d5db;
		background: white;
		margin-top: 2px;
		transition: all 0.15s ease;
	}

	.radio-indicator.checked {
		border-color: #3b82f6;
		background: #3b82f6;
		color: white;
	}

	.option-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border-radius: 10px;
		background: #f3f4f6;
		color: #6b7280;
	}

	.option-button:hover:not(:disabled) .option-icon {
		background: #dbeafe;
		color: #3b82f6;
	}

	.option-content {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}

	.option-label {
		font-weight: 600;
		font-size: 15px;
		color: #1f2937;
	}

	.option-description {
		font-size: 13px;
		color: #6b7280;
		line-height: 1.4;
	}

	.help-text {
		margin-top: 16px;
		margin-bottom: 0;
		font-size: 13px;
		color: #6b7280;
		line-height: 1.5;
	}
</style>
