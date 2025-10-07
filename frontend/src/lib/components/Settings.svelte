<script lang="ts">
	import {photoCaptureSettings} from '$lib/stores';

	export let onSaveSuccess = (message: string) => {};
	export let onSaveError = (message: string) => {};
	export let onCancel = () => {};

	let shutterSoundEnabled = $photoCaptureSettings.shutterSoundEnabled;

	function saveSettings() {
		try {
			photoCaptureSettings.update(settings => ({
				...settings,
				shutterSoundEnabled
			}));

			onSaveSuccess('Settings saved successfully');
		} catch (error) {
			console.error('Failed to save settings:', error);
			onSaveError('Failed to save settings');
		}
	}

	// Watch for changes and auto-save
	$: if (shutterSoundEnabled !== $photoCaptureSettings.shutterSoundEnabled) {
		saveSettings();
	}
</script>

<h2>Camera Settings</h2>

<div class="form-group">
	<label class="toggle-label">
		<input
			type="checkbox"
			bind:checked={shutterSoundEnabled}
			data-testid="shutter-sound-toggle"
		/>
		<span class="toggle-text">Enable shutter sound</span>
	</label>
	<p class="help-text">
		Play a sound when taking photos with the camera.
	</p>
</div>

<div class="form-actions">
	<button type="button" class="cancel-button" on:click={onCancel}>
		Close Settings
	</button>
</div>

<style>
	h2 {
		margin-bottom: 1.5rem;
		color: #1f2937;
	}

	.form-group {
		margin-bottom: 1.5rem;
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		cursor: pointer;
		font-weight: 500;
		color: #1f2937;
	}

	.toggle-label input[type="checkbox"] {
		width: 1rem;
		height: 1rem;
		cursor: pointer;
	}

	.toggle-text {
		user-select: none;
	}

	.help-text {
		margin-top: 0.5rem;
		margin-left: 1.75rem;
		font-size: 0.875rem;
		color: #6b7280;
		line-height: 1.4;
	}

	.form-actions {
		margin-top: 2rem;
		display: flex;
		justify-content: flex-end;
	}

	.cancel-button {
		padding: 0.5rem 1rem;
		background-color: #f3f4f6;
		color: #374151;
		border: 1px solid #d1d5db;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.cancel-button:hover {
		background-color: #e5e7eb;
		border-color: #9ca3af;
	}
</style>