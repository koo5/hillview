<script lang="ts">
	import {onMount} from 'svelte';
	import {TAURI} from "$lib/tauri.js";
	import {auth} from '$lib/auth.svelte';
	import type {User} from '$lib/auth.svelte';
	import {navigateWithHistory} from '$lib/navigation.svelte';
	import {autoUploadSettings} from "$lib/autoUploadSettings";
	import LicenseSelector from './LicenseSelector.svelte';
	import {photoLicense} from '$lib/data.svelte';

	export let onSaveSuccess = (message: string) => {
	};

	export let onCancel: (() => void) | null = null;

	let autoUploadEnabled = false;
	let autoUploadPromptEnabled = true;
	let user: User | null = null;
	let alert: { type: string, message: string } | null = null;

	// Computed property for radio button state
	$: radioState = autoUploadEnabled ? 'enabled' :
		(!autoUploadPromptEnabled ? 'disabled_never' : 'disabled');

	onMount(() => {
		// Subscribe to auth state changes
		const unsubscribe1 = auth.subscribe(authState => {
			user = authState.is_authenticated ? authState.user : null;
		});

		const unsubscribe2 = autoUploadSettings.subscribe(value => {
			//console.log('Auto-upload settings loaded:', JSON.stringify(value));
			autoUploadEnabled = value.value?.auto_upload_enabled || false;
			autoUploadPromptEnabled = value.value?.auto_upload_prompt_enabled !== false;
		});

		// Return cleanup function
		return () => {
			unsubscribe1();
			unsubscribe2();
		};
	});

	async function saveSettings() {
		await autoUploadSettings.persist(
			{
				auto_upload_enabled: autoUploadEnabled,
				auto_upload_prompt_enabled: autoUploadPromptEnabled
			}
		);

		const statusText = autoUploadEnabled ? 'enabled' :
			!autoUploadPromptEnabled ? 'disabled (never prompt)' : 'disabled';
		const msg = `Auto-upload ${statusText}`;
		onSaveSuccess(msg);
		alert = {type: 'success', message: msg};

		if (onCancel) {
			onCancel();
		}
	}

	function handleRadioChange(value: string) {
		switch (value) {
			case 'enabled':
				autoUploadEnabled = true;
				autoUploadPromptEnabled = true;
				break;
			case 'disabled':
				autoUploadEnabled = false;
				autoUploadPromptEnabled = true;
				break;
			case 'disabled_never':
				autoUploadEnabled = false;
				autoUploadPromptEnabled = false;
				break;
		}
		saveSettings();
	}

	function goToLogin() {
		navigateWithHistory('/login');
	}
</script>

{#if TAURI}
	<h2>Auto-Upload Settings</h2>

	<!-- License Selector -->
	<div class="form-group">
		<LicenseSelector required={true} showDescription={false} />
		{#if $photoLicense === null}
			<div class="license-warning">
				Auto-upload is disabled until you select a license for your photos.
			</div>
		{/if}
	</div>

	<div class="form-group">
		<p class="help-text">
			Automatically upload photos taken with the app's camera, to be visible in hillview.cz and in the app.
		</p>
		<div class="radio-group" class:disabled={$photoLicense === null}>
			<label>
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'enabled'}
					   on:change={() => handleRadioChange('enabled')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-enabled"/>
				Enabled
			</label>
			<label>
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'disabled'}
					   on:change={() => handleRadioChange('disabled')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-disabled"/>
				Disabled
			</label>
			<label>
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'disabled_never'}
					   on:change={() => handleRadioChange('disabled_never')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-disabled-never"/>
				Disabled (Never prompt)
			</label>
		</div>
		{#if !user && autoUploadEnabled}
			<div class="login-notice {autoUploadEnabled ? 'urgent-login-notice' : ''}">
				<p>Please
					<button type="button" class="login-link" on:click={goToLogin}>log in</button>
					to upload photos.
				</p>
			</div>
		{/if}
	</div>

	<div class="button-group">
		{#if onCancel}
			<button class="secondary-button" on:click={onCancel}>Cancel</button>
		{/if}
	</div>
{:else}
	<p>Auto-upload settings are only available in the mobile application.</p>
{/if}

{#if alert}
	<div class="alert {alert.type}" data-testid="alert-message">
		{alert.message}
	</div>
{/if}


<style>
	.radio-group {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-top: 1rem;
	}

	.radio-group label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
	}

	.radio-group input[type="radio"] {
		cursor: pointer;
	}

	button {
		margin-top: 1rem;
	}

	.alert {
		margin-top: 1rem;
		padding: 0.75rem 1rem;
		border-radius: 4px;
	}

	.alert.success {
		background-color: #d4edda;
		color: #155724;
	}

	.alert.error {
		background-color: #f8d7da;
		color: #721c24;
	}

</style>
