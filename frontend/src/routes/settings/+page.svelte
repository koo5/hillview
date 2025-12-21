<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import CameraSettings from '$lib/components/CameraSettings.svelte';
	import UploadSettingsComponent from '$lib/components/UploadSettings.svelte';
	import NotificationSettingsComponent from '$lib/components/NotificationSettings.svelte';
	import DebugSettings from '$lib/components/DebugSettings.svelte';
	import type { Alert } from '$lib/alertSystem.svelte';
	import {Database, Settings} from "lucide-svelte";
	import {TAURI} from "$lib/tauri";

	let alertMessage = '';
	let alertType: Alert['type'] = 'info';

	function showAlert(message: string, type: Alert['type'] = 'info') {
		alertMessage = message;
		alertType = type;
		setTimeout(() => {
			alertMessage = '';
		}, 3000);
	}
</script>


<StandardHeaderWithAlert
	title="Settings"
	showMenuButton={true}
	fallbackHref="/"
	{alertMessage}
	{alertType}
/>

<StandardBody>

	<div class="settings-container">

		<!-- Notification Settings -->
		{#if TAURI}
		<div class="section-divider"></div>
		<NotificationSettingsComponent
			onSaveSuccess={(message) => showAlert(message, 'success')}
			onSaveError={(message) => showAlert(message, 'error')}
		/>
		{/if}

		{#if TAURI}
		<CameraSettings
			onSaveSuccess={(message) => showAlert(message, 'success')}
			onSaveError={(message) => showAlert(message, 'error')}
		/>
		{/if}

		{#if TAURI}
		<div class="section-divider"></div>
		<UploadSettingsComponent
			onSaveSuccess={(message) => showAlert(message, 'success')}
		/>
		{/if}

		<!-- Advanced Settings -->
		<div class="section-divider"></div>
		<h2>Advanced</h2>
		<a href="/settings/advanced" class="settings-navigation-link" data-testid="advanced-menu-link">
			<Settings size={18} />
			<div class="link-text">
				<span class="link-title">Advanced Settings</span>
				<span class="link-description">Configure advanced options and developer settings</span>
			</div>
		</a>



	</div>

</StandardBody>

<style>
	.settings-container {
		padding: 20px;
		max-width: 600px;
		margin: 0 auto;
	}

	.section-divider {
		height: 1px;
		background-color: #e5e7eb;
	}


	.settings-navigation-link {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem 0;
		text-decoration: none;
		color: #374151;
		border-radius: 0.375rem;
		transition: background-color 0.2s ease;
	}

	.settings-navigation-link:hover {
		background-color: #f9fafb;
		padding-left: 0.5rem;
		padding-right: 0.5rem;
	}

	.link-text {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.link-title {
		font-weight: 500;
		font-size: 0.875rem;
	}

	.link-description {
		font-size: 0.75rem;
		color: #6b7280;
		line-height: 1.3;
	}
</style>
