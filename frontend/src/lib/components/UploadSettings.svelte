<script lang="ts">
	import {onMount} from 'svelte';
	import {TAURI} from "$lib/tauri.js";
	import {auth} from '$lib/auth.svelte';
	import type {User} from '$lib/auth.svelte';
	import {navigateWithHistory} from '$lib/navigation.svelte';
	import {autoUploadSettings} from "$lib/autoUploadSettings";
	import LicenseSelector from './LicenseSelector.svelte';
	import {photoLicense} from '$lib/data.svelte';
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";
	import MyExternalLink from "$lib/components/MyExternalLink.svelte";

	export let onSaveSuccess = (message: string) => {
	};

	export let onCancel: (() => void) | null = null;

	let autoUploadEnabled = false;
	let autoUploadPromptEnabled = true;
	let wifiOnly = true;
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
			wifiOnly = value.value?.wifi_only !== false;
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
				auto_upload_prompt_enabled: autoUploadPromptEnabled,
				wifi_only: wifiOnly
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
	<SettingsSectionHeader>Auto-Upload</SettingsSectionHeader>
		<p class="help-text">
			Automatically upload photos taken with the app's camera, to be visible in <MyExternalLink href="https://hillview.cz" >hillview.cz</MyExternalLink>
                and in the app.
		</p>

	<div class="form-group">

		<LicenseSelector required={true} />

		<div class="radio-group" class:disabled={$photoLicense === null}>
			<label class="radio-option">
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'enabled'}
					   on:change={() => handleRadioChange('enabled')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-enabled"/>
				<div class="option-content">
					<span class="option-title">Enabled</span>
					<span class="option-description">Photos are uploaded automatically after capture</span>
				</div>
			</label>
			<label class="radio-option">
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'disabled'}
					   on:change={() => handleRadioChange('disabled')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-disabled"/>
				<div class="option-content">
					<span class="option-title">Disabled</span>
					<span class="option-description">Ask me each time whether to upload</span>
				</div>
			</label>
			<label class="radio-option">
				<input type="radio"
					   name="autoUpload"
					   checked={radioState === 'disabled_never'}
					   on:change={() => handleRadioChange('disabled_never')}
					   disabled={$photoLicense === null}
					   data-testid="auto-upload-disabled-never"/>
				<div class="option-content">
					<span class="option-title">Disabled (Never prompt)</span>
					<span class="option-description">Don't upload and don't ask</span>
				</div>
			</label>
		</div>

		{#if autoUploadEnabled}
			<div class="checkbox-option">
				<label>
					<input type="checkbox"
						   bind:checked={wifiOnly}
						   on:change={saveSettings}
						   data-testid="wifi-only-checkbox"/>
					<span class="checkbox-label">Only upload on Wi-Fi</span>
				</label>
				<span class="checkbox-description">Prevent uploads over mobile data to save bandwidth</span>
			</div>
		{/if}

		{#if !user && autoUploadEnabled}
			<div class="urgent-login-notice">
				<p>Please
					<button type="button" class="login-link" on:click={goToLogin}>log in</button>
					to upload photos.
				</p>
			</div>
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

	.radio-group.disabled {
		opacity: 0.5;
		pointer-events: none;
	}

	.radio-option {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: border-color 0.2s, background-color 0.2s;
	}

	.radio-option:hover {
		border-color: #d1d5db;
		background-color: #f9fafb;
	}

	.radio-option:has(input:checked) {
		border-color: #3b82f6;
		background-color: #eff6ff;
	}

	.radio-option input {
		margin-top: 0.125rem;
		flex-shrink: 0;
	}

	.option-content {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.option-title {
		font-weight: 500;
		font-size: 0.875rem;
		color: #1f2937;
	}

	.option-description {
		font-size: 0.75rem;
		color: #6b7280;
		line-height: 1.4;
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

	.login-notice {
		background: #fff3cd;
		color: #856404;
		padding: 0.75em;
		border-radius: 6px;
		margin-top: 0.5em;
	}

	.urgent-login-notice {
		background: #f8d7da;
		color: #721c24;
		font-weight: bold;
		border: 2px solid #dc3545;
		animation: urgentPulse 1s infinite alternate;
	}

	.checkbox-option {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin-top: 1rem;
		padding: 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 0.5rem;
		background-color: #f9fafb;
	}

	.checkbox-option label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
	}

	.checkbox-label {
		font-weight: 500;
		font-size: 0.875rem;
		color: #1f2937;
	}

	.checkbox-description {
		font-size: 0.75rem;
		color: #6b7280;
		line-height: 1.4;
		margin-left: 1.5rem;
	}

</style>
