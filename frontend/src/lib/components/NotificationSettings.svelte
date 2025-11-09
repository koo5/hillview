<script lang="ts">
	import { onMount } from 'svelte';
	import { Bell, BellOff, AlertTriangle } from 'lucide-svelte';
	import { invoke } from '@tauri-apps/api/core';

	// Type definitions for API responses
	interface NotificationSettingsResponse {
		enabled: boolean;
		success: boolean;
		error?: string;
	}

	interface PermissionResponse {
		granted: boolean;
		success: boolean;
		error?: string;
	}

	interface BasicResponse {
		success: boolean;
		error?: string;
	}

	export let onSaveSuccess = (message: string) => {};
	export let onSaveError = (message: string) => {};

	let notificationsEnabled = true;
	let permissionGranted = true;
	let isLoading = false;
	let lastError: string | null = null;

	// Load current notification settings
	async function loadNotificationSettings() {
		isLoading = true;
		lastError = null;

		try {
			// Get user-level notification setting
			const settingsResult = await invoke<NotificationSettingsResponse>('plugin:hillview|get_notification_settings');
			if (settingsResult.success) {
				notificationsEnabled = settingsResult.enabled;
			}

			// Check system notification permission status
			const permissionResult = await invoke<PermissionResponse>('plugin:hillview|check_notification_permission');
			permissionGranted = permissionResult.granted || false;

		} catch (error) {
			console.error('Failed to load notification settings:', error);
			const errorMessage = error instanceof Error ? error.message : 'Failed to load notification settings';
			lastError = errorMessage;
			onSaveError(lastError);
		} finally {
			isLoading = false;
		}
	}

	// Request notification permission from Android
	async function requestNotificationPermission() {
		isLoading = true;
		lastError = null;

		try {
			const result = await invoke<PermissionResponse>('plugin:hillview|request_notification_permission');

			if (result.granted) {
				permissionGranted = true;
				onSaveSuccess('Notification permission granted');
			} else {
				permissionGranted = false;
				const errorMsg = result.error || 'Notification permission denied';
				lastError = errorMsg;
				onSaveError(errorMsg);
			}

		} catch (error) {
			console.error('Failed to request notification permission:', error);
			const errorMessage = error instanceof Error ? error.message : 'Failed to request notification permission';
			lastError = errorMessage;
			onSaveError(errorMessage);
		} finally {
			isLoading = false;
		}
	}

	// Toggle notifications enabled/disabled
	async function toggleNotifications(event: Event) {
		// Prevent default checkbox behavior so we can manage state manually
		event.preventDefault();

		isLoading = true;
		lastError = null;

		try {
			const newState = !notificationsEnabled;

			// If enabling notifications, check/request permission first
			if (newState && !permissionGranted) {
				await requestNotificationPermission();

				// Only proceed if permission was granted
				if (!permissionGranted) {
					isLoading = false;
					return;
				}
			}

			// Save setting to Android SharedPreferences
			const result = await invoke<BasicResponse>('plugin:hillview|set_notification_settings', { enabled: newState });

			if (result.success) {
				notificationsEnabled = newState;
				onSaveSuccess(
					notificationsEnabled
						? 'Notifications enabled'
						: 'Notifications disabled'
				);
			} else {
				const errorMessage = result.error || 'Failed to save notification settings';
				lastError = errorMessage;
				onSaveError(errorMessage);
			}

		} catch (error) {
			console.error('Failed to toggle notifications:', error);
			const errorMessage = error instanceof Error ? error.message : 'Failed to toggle notifications';
			lastError = errorMessage;
			onSaveError(errorMessage);
		} finally {
			isLoading = false;
		}
	}

	onMount(() => {
		loadNotificationSettings();
	});
</script>

<div class="notification-settings">
	<h3>
		{#if notificationsEnabled}
			<Bell size={20} />
		{:else}
			<BellOff size={20} />
		{/if}
		Notifications
	</h3>

	<!-- Main notification toggle -->
	<div class="setting-item">
		<label class="toggle-label">
			<input
				type="checkbox"
				checked={notificationsEnabled}
				on:click={toggleNotifications}
				disabled={isLoading}
			/>
			<span class="toggle-slider"></span>
			<div class="toggle-text">
				<strong>Enable Notifications</strong>
				<span class="toggle-description">
					Show system notifications for authentication, uploads, and other app events
				</span>
			</div>
		</label>
	</div>

	<!-- Permission status -->
	{#if notificationsEnabled && !permissionGranted}
		<div class="permission-warning">
			<AlertTriangle size={16} />
			<div>
				<p><strong>Permission Required</strong></p>
				<p>Notification permission is needed to show system notifications.</p>
				<button
					class="permission-button"
					on:click={requestNotificationPermission}
					disabled={isLoading}
				>
					{isLoading ? 'Requesting...' : 'Grant Permission'}
				</button>
			</div>
		</div>
	{/if}

	<!-- Help text -->
	<div class="help-section">
		<details>
			<summary>About Notifications</summary>
			<p>
				Notifications are separate from push messaging. You can receive push messages
				to wake up the app even if notifications are disabled. Enabling notifications
				allows the app to show system notifications for important events like
				authentication expiry or upload status.
			</p>
		</details>
	</div>

	{#if lastError}
		<div class="error-message">
			{lastError}
		</div>
	{/if}
</div>

<style>
	.notification-settings {
		margin-bottom: 2rem;
	}

	h3 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 1rem;
		font-size: 1.125rem;
		font-weight: 600;
		color: #374151;
	}

	.setting-item {
		margin-bottom: 1rem;
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 1rem;
		cursor: pointer;
		padding: 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid #e5e7eb;
		background: #f9fafb;
		transition: all 0.2s ease;
	}

	.toggle-label:hover {
		background: #f3f4f6;
		border-color: #d1d5db;
	}

	input[type="checkbox"] {
		display: none;
	}

	.toggle-slider {
		position: relative;
		width: 3rem;
		height: 1.5rem;
		background: #d1d5db;
		border-radius: 1rem;
		transition: background 0.3s ease;
		flex-shrink: 0;
	}

	.toggle-slider::after {
		content: '';
		position: absolute;
		top: 0.125rem;
		left: 0.125rem;
		width: 1.25rem;
		height: 1.25rem;
		background: white;
		border-radius: 50%;
		transition: transform 0.3s ease;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	input:checked + .toggle-slider {
		background: #22c55e;
	}

	input:checked + .toggle-slider::after {
		transform: translateX(1.5rem);
	}

	input:disabled + .toggle-slider {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.toggle-text {
		flex: 1;
	}

	.toggle-description {
		display: block;
		color: #6b7280;
		font-size: 0.875rem;
		margin-top: 0.25rem;
	}

	.permission-warning {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.875rem;
		background: #fef3c7;
		border: 1px solid #fbbf24;
		border-radius: 0.5rem;
		margin-bottom: 1rem;
	}

	.permission-warning p {
		margin: 0 0 0.5rem 0;
		color: #92400e;
		font-size: 0.875rem;
	}

	.permission-button {
		background: #f59e0b;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 0.375rem;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.2s ease;
	}

	.permission-button:hover {
		background: #d97706;
	}

	.permission-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.help-section {
		margin-top: 1rem;
	}

	.help-section details {
		cursor: pointer;
	}

	.help-section summary {
		color: #4f46e5;
		font-size: 0.875rem;
		font-weight: 500;
		margin-bottom: 0.5rem;
		user-select: none;
	}

	.help-section p {
		color: #6b7280;
		font-size: 0.875rem;
		line-height: 1.5;
		margin: 0;
		padding-left: 1rem;
	}

	.error-message {
		color: #dc2626;
		background: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 0.5rem;
		padding: 0.75rem;
		font-size: 0.875rem;
		margin-top: 1rem;
	}
</style>