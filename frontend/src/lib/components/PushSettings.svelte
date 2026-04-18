<script lang="ts">
	import {onMount} from 'svelte';
	import {TAURI} from "$lib/tauri.js";
	import {invoke} from '@tauri-apps/api/core';
	import { Smartphone, Wifi, WifiOff, CheckCircle, AlertCircle, Clock } from 'lucide-svelte';
	import { addAlert } from '$lib/alertSystem.svelte';
	import MyExternalLink from './MyExternalLink.svelte';
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";
	import {app} from "$lib/data.svelte";

	const FCM_DIRECT_PACKAGE = 'com.google.firebase.messaging.direct';

	let distributors: PushDistributorInfo[] = [];
	let selectedDistributor = '';
	let registrationStatus = '';
	let statusMessage = '';
	let isLoading = false;
	let lastError: string | null = null;

	// Debug reactive statement to track state changes
	$: console.log('🔄 Reactive update - isLoading:', isLoading, 'distributors.length:', distributors.length);

	interface PushDistributorInfo {
		package_name: string;
		display_name: string;
		is_available: boolean;
	}

	interface PushDistributorsResponse {
		distributors: PushDistributorInfo[];
		success: boolean;
		error?: string;
	}

	interface PushRegistrationStatusResponse {
		status: string;
		status_message: string;
		selected_distributor?: string;
		last_error?: string;
		success: boolean;
		error?: string;
	}

	onMount(() => {
		if (TAURI) {
			loadPushSettings();
		}
	});

	async function loadPushDistributors() {
		console.log('📡 Loading push distributors...');
		const distributorsResult = await invoke('plugin:hillview|get_push_distributors') as PushDistributorsResponse;
		console.log('📡 Distributors result:', distributorsResult);

		if (distributorsResult.success) {
			distributors = distributorsResult.distributors;
			console.log('✅ Distributors loaded:', distributors.length, 'items');
		} else {
			console.error('❌ Failed to load distributors:', distributorsResult.error);
			throw new Error(distributorsResult.error || 'Failed to load distributors');
		}
	}

	async function loadPushStatus() {
		console.log('📡 Loading push registration status...');
		const statusResult = await invoke('plugin:hillview|get_push_registration_status') as PushRegistrationStatusResponse;
		console.log('📡 Status result:', JSON.stringify(statusResult));

		if (statusResult.success) {
			registrationStatus = statusResult.status;
			statusMessage = statusResult.status_message;
			selectedDistributor = statusResult.selected_distributor || '';
			lastError = statusResult.last_error || null;
			console.log('✅ Status loaded:', { registrationStatus, statusMessage, selectedDistributor });
		} else {
			console.error('❌ Failed to load status:', statusResult.error);
			throw new Error(statusResult.error || 'Failed to load status');
		}
	}

	async function loadPushSettings() {
		try {
			console.log('🔄 Loading push settings...');
			isLoading = true;

			await loadPushDistributors();
			await loadPushStatus();

		} catch (err) {
			console.error('❌ Error loading push settings:', err);
			addAlert(`Failed to load push notification settings: ${err}`, 'error');
		} finally {
			isLoading = false;
			console.log('🏁 Loading push distributor settings complete. isLoading:', false, 'distributors:', distributors.length);
		}
	}

	async function selectDistributor(packageName: string) {
		try {
			console.log('🎯 Starting distributor selection:', packageName);
			isLoading = true;

			console.log('📡 Calling select_push_distributor...');
			const result = await invoke('plugin:hillview|select_push_distributor', {
				request: { package_name: packageName }
			}) as { success: boolean; error?: string };
			console.log('📡 Selection result:', JSON.stringify(result));

			if (result.success) {
				selectedDistributor = packageName;
				console.log('✅ Distributor selected successfully:', packageName);
				addAlert(packageName ? 'Push distributor selected successfully' : 'Push notifications disabled', 'success');

				// Reload status after selection
				console.log('🔄 Reloading status after selection...');
				await loadPushStatus();
				console.log('🎯 Selection complete!');
			} else {
				console.error('❌ Selection failed:', result.error);
				throw new Error(result.error || 'Failed to select distributor');
			}

		} catch (err) {
			console.error('❌ Error selecting distributor:', err);
			addAlert(`Failed to select push distributor: ${err}`, 'error');
		} finally {
			isLoading = false;
			console.log('🏁 Distributor selection complete. isLoading:', false, 'distributors:', distributors.length);
		}
	}

	function getStatusColor(status: string): string {
		switch (status) {
			case 'registered': return 'text-green-600';
			case 'distributor_missing':
			case 'registration_failed': return 'text-red-600';
			case 'not_configured': return 'text-gray-600';
			case 'disabled': return 'text-gray-500';
			default: return 'text-gray-600';
		}
	}

	function getStatusIcon(status: string): string {
		switch (status) {
			case 'registered': return '✅';
			case 'distributor_missing': return '⚠️';
			case 'registration_failed': return '❌';
			case 'not_configured': return '⚙️';
			case 'disabled': return '🔇';
			default: return '❓';
		}
	}
</script>

<div class="push-settings-container">
	<SettingsSectionHeader>Push Notifications</SettingsSectionHeader>

	{#if !TAURI}
		<div class="not-available">
			<p>Push notifications are only available on mobile devices.</p>
		</div>
	{:else if isLoading}
		<div class="loading">
			<p>Loading push notification settings...</p>
		</div>
	{:else}
		<!-- Current Status -->
		<div class="status-section">
			<h3>Current Status</h3>
			<div class="status-display {getStatusColor(registrationStatus)}">
				<span class="status-icon">{getStatusIcon(registrationStatus)}</span>
				<span class="status-text">{statusMessage}</span>
			</div>

			{#if lastError}
				<div class="error-message">
					<strong>Last Error:</strong> {lastError}
				</div>
			{/if}
		</div>

		<!-- Distributor Selection -->
		<div class="distributor-section">
			<h3>Push Notification Provider</h3>
			<p class="description">
				Choose your preferred push notification distributor.
			</p>

			<div class="distributor-options">
				<!-- Available distributors -->
				{#each distributors as distributor}
					{@const isUp = distributor.package_name !== FCM_DIRECT_PACKAGE}
					{@const upGated = isUp && !$app.debug_enabled}
					<label
						class="distributor-option"
						class:unavailable={!distributor.is_available || upGated}
						data-testid="push-distributor-option"
					>
						<input
							type="radio"
							bind:group={selectedDistributor}
							value={distributor.package_name}
							on:change={() => selectDistributor(distributor.package_name)}
							disabled={isLoading || !distributor.is_available || upGated}
						/>
						<div class="option-content">
							<div class="option-header">
								<span class="option-icon">
									{#if distributor.is_available}
										📱
									{:else}
										⚠️
									{/if}
								</span>
								<span class="option-name">{distributor.display_name}</span>
								{#if !distributor.is_available}
									<span class="unavailable-badge">Not Available</span>
								{/if}
								{#if isUp}
									<span class="wip-badge" data-testid="push-up-wip-badge">WIP</span>
								{/if}
							</div>
							<div class="option-description">
								{#if distributor.is_available}
									Package: {distributor.package_name}
								{:else}
									App not installed: {distributor.package_name}
								{/if}
							</div>
							{#if isUp}
								<div class="wip-note" data-testid="push-up-wip-note">
									UnifiedPush support is still a work in progress.{#if upGated} Enable debug mode in Advanced Settings to try it.{/if}
								</div>
							{/if}
						</div>
					</label>
				{/each}

				<!-- Disabled option -->
				<label class="distributor-option">
					<input
						type="radio"
						bind:group={selectedDistributor}
						value=""
						on:change={() => selectDistributor('')}
						disabled={isLoading}
					/>
					<div class="option-content">
						<div class="option-header">
							<span class="option-icon">🔇</span>
							<span class="option-name">Push notifications disabled</span>
						</div>
						<div class="option-description">
							Turn off push notifications
						</div>
					</div>
				</label>

			</div>
		</div>
	{/if}
</div>

<style>
	.push-settings-container {
		max-width: 100%;
	}

	.not-available, .loading {
		padding: 1rem;
		text-align: center;
		color: #6b7280;
		font-style: italic;
	}

	.status-section {
		margin-bottom: 2rem;
		padding: 1rem;
		background-color: #f9fafb;
		border-radius: 0.5rem;
		border: 1px solid #e5e7eb;
	}

	.status-display {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 500;
		margin-top: 0.5rem;
	}

	.status-icon {
		font-size: 1.2rem;
	}

	.error-message {
		margin-top: 0.5rem;
		padding: 0.5rem;
		background-color: #fef2f2;
		border: 1px solid #fecaca;
		border-radius: 0.25rem;
		color: #dc2626;
		font-size: 0.875rem;
	}

	.distributor-section {
		margin-bottom: 2rem;
	}

	.description {
		color: #6b7280;
		margin-bottom: 1rem;
		line-height: 1.5;
	}

	.distributor-options {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.distributor-option {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 1rem;
		border: 2px solid #e5e7eb;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.distributor-option:hover:not(.unavailable) {
		border-color: #3b82f6;
		background-color: #f8fafc;
	}

	.distributor-option.unavailable {
		opacity: 0.6;
		cursor: not-allowed;
		background-color: #f9fafb;
	}

	.distributor-option input[type="radio"] {
		margin: 0;
		margin-top: 0.125rem;
	}

	.option-content {
		flex: 1;
	}

	.option-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 500;
		margin-bottom: 0.25rem;
	}

	.option-icon {
		font-size: 1.1rem;
	}

	.option-name {
		color: #1f2937;
	}

	.unavailable-badge {
		background-color: #fbbf24;
		color: #92400e;
		font-size: 0.75rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		border-radius: 0.75rem;
	}

	.wip-badge {
		background-color: #e0e7ff;
		color: #3730a3;
		font-size: 0.75rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		border-radius: 0.75rem;
	}

	.wip-note {
		margin-top: 0.5rem;
		font-size: 0.8125rem;
		font-style: italic;
		color: #6b7280;
		line-height: 1.4;
	}

	.option-description {
		color: #6b7280;
		font-size: 0.875rem;
		line-height: 1.4;
	}

	h3 {
		color: #1f2937;
		margin-bottom: 1rem;
		font-size: 1.125rem;
		font-weight: 500;
	}
</style>
