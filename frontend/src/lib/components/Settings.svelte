<script lang="ts">
	import {onMount} from 'svelte';
	import {get} from 'svelte/store';
	import {TAURI} from "$lib/tauri.js";
	import {invoke} from '@tauri-apps/api/core';
	import {auth} from '$lib/auth.svelte';
	import type {User} from '$lib/auth.svelte';
	import {navigateWithHistory} from '$lib/navigation.svelte';

	export let onSaveSuccess = (message: string) => {};
	export let onSaveError = (message: string) => {};
	export let onCancel: (() => void) | null = null;

	let autoUploadEnabled = false;
	let autoUploadPromptEnabled = true;
	let user: User | null = null;
	let alert = null;

	// Computed property for radio button state
	$: radioState = autoUploadEnabled ? 'enabled' :
	               (!autoUploadPromptEnabled ? 'disabled_never' : 'disabled');

	onMount(() => {
		// Subscribe to auth state changes
		const unsubscribe = auth.subscribe(authState => {
			user = authState.isAuthenticated ? authState.user : null;
		});

		// Load auto-upload setting if on Tauri
		if (TAURI) {
			loadAndroidAutoUploadSetting();
		}

		// Return cleanup function
		return () => {
			unsubscribe();
		};
	});

	async function loadAndroidAutoUploadSetting() {
		try {
			const result = await invoke('plugin:hillview|get_upload_status') as {
				autoUploadEnabled: boolean;
				autoUploadPromptEnabled: boolean;
			};

			autoUploadEnabled = result.autoUploadEnabled || false;
			autoUploadPromptEnabled = result.autoUploadPromptEnabled !== false; // Default to true
			console.log('📱 Loaded Android auto-upload settings:', {autoUploadEnabled, autoUploadPromptEnabled});
		} catch (err) {
			console.error('Failed to load Android auto-upload settings:', err);
			onSaveError('Failed to load settings. Using defaults.');
			// Use defaults instead of crashing
			autoUploadEnabled = false;
			autoUploadPromptEnabled = true;
		}
	}

	async function saveSettings() {
		if (TAURI) {
			try {
				console.log('📤 Setting Android auto-upload:', JSON.stringify({autoUploadEnabled, autoUploadPromptEnabled}));
				await invoke('plugin:hillview|set_auto_upload_enabled', {
					enabled: autoUploadEnabled,
					promptEnabled: autoUploadPromptEnabled
				});

				const statusText = autoUploadEnabled ? 'enabled' :
								  !autoUploadPromptEnabled ? 'disabled (never prompt)' : 'disabled';
				const msg = `Auto-upload ${statusText}`;
				onSaveSuccess(msg);
				alert = {type: 'success', message: msg};

				if (onCancel) {
					onCancel();
				}
			} catch (err) {
				console.error('Error updating Android plugin:', err);
				onSaveError('Failed to save settings');
			}
		}
	}

	function handleRadioChange(value: string) {
		switch(value) {
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
	}

	function goToLogin() {
		navigateWithHistory('/login');
	}
</script>

{#if TAURI}
	<h2>Auto-Upload Settings</h2>
	<div class="form-group">
		<p class="help-text">
			Automatically upload photos taken with the app's camera to your account.
		</p>
		<div class="radio-group">
			<label>
				<input type="radio"
					name="autoUpload"
					checked={radioState === 'enabled'}
					on:change={() => handleRadioChange('enabled')}
					data-testid="auto-upload-enabled"/>
				Enabled
			</label>
			<label>
				<input type="radio"
					name="autoUpload"
					checked={radioState === 'disabled'}
					on:change={() => handleRadioChange('disabled')}
					data-testid="auto-upload-disabled"/>
				Disabled
			</label>
			<label>
				<input type="radio"
					name="autoUpload"
					checked={radioState === 'disabled_never'}
					on:change={() => handleRadioChange('disabled_never')}
					data-testid="auto-upload-disabled-never"/>
				Disabled (Never prompt)
			</label>
		</div>
		{#if !user}
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
		<button class="primary-button" on:click={saveSettings} data-testid="save-settings-button"
				disabled={autoUploadEnabled && !user}>Save Settings
		</button>
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
