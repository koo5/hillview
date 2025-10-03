<script lang="ts">
	import {photoCaptureSettings} from '$lib/stores';

	export let onSaveSuccess = (message: string) => {};
	export let onSaveError = (message: string) => {};

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
</style>