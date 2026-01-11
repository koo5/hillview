<svelte:head>
	<title>Advanced Settings - Hillview</title>
</svelte:head>

<script lang="ts">
	import { onMount } from 'svelte';
	import { Database, Wifi, ChevronRight } from "lucide-svelte";
	import { TAURI } from "$lib/tauri";
	import { invoke } from '@tauri-apps/api/core';
	import DebugSettings from "$lib/components/DebugSettings.svelte";
	import StandardHeaderWithAlert from "$lib/components/StandardHeaderWithAlert.svelte";
	import StandardBody from "$lib/components/StandardBody.svelte";
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";
	import SettingsSectionDivider from "$lib/components/SettingsSectionDivider.svelte";

	let autoExportEnabled = false;

	onMount(async () => {
		if (TAURI) {
			try {
				const result = await invoke('plugin:hillview|cmd', {
					command: 'geo_tracking_get_auto_export'
				}) as { enabled: boolean };
				autoExportEnabled = result.enabled;
			} catch (error) {
				console.error('Failed to get auto export setting:', error);
			}
		}
	});

	async function handleExport() {
		try {
			await invoke('plugin:hillview|cmd', { command: 'geo_tracking_export' });
			alert('Location and orientation data exported successfully.');
		} catch (error) {
			console.error('Export failed:', error);
			alert('Failed to export location and orientation data.');
		}
	}

	async function handleAutoExportChange(event: Event) {
		const target = event.target as HTMLInputElement;
		const enabled = target.checked;
		try {
			await invoke('plugin:hillview|cmd', {
				command: 'geo_tracking_set_auto_export',
				params: { enabled }
			});
			autoExportEnabled = enabled;
		} catch (error) {
			console.error('Failed to update auto export setting:', error);
			alert('Failed to update automatic export setting.');
			// Revert checkbox state
			target.checked = !enabled;
		}
	}
</script>

<StandardHeaderWithAlert
	title="Advanced Settings"
	showMenuButton={true}
	fallbackHref="/settings"
/>

<StandardBody>

		<SettingsSectionDivider />
		<SettingsSectionHeader>Advanced Settings</SettingsSectionHeader>

		{#if TAURI}
		<a href="/settings/push" class="settings-navigation-link" data-testid="push-messaging-link">
			<Wifi size={18}/>
			<div class="link-text">
				<span class="link-title">Push Messaging</span>
				<span class="link-description">Configure push notification providers</span>
			</div>
			<ChevronRight size={16} />
		</a>
		{/if}

		<a href="/settings/sources" class="settings-navigation-link" data-testid="sources-menu-link">
			<Database size={18}/>
			<div class="link-text">
				<span class="link-title">Sources</span>
				<span class="link-description">Configure alternative photo API endpoints</span>
			</div>
			<ChevronRight size={16} />
		</a>

		<SettingsSectionDivider />
		<DebugSettings />

	{#if TAURI}
		<SettingsSectionDivider />
		<SettingsSectionHeader>Location/Orientation Data</SettingsSectionHeader>

		<p>The app stores location and orientation data for the duration of a session, and clears them when the app is closed or restarted. You can export this data for purposes of embedding them into photos created outside of Hillview.</p>

		<p>
			This will create files named hillview_orientations_[timestamp].csv and hillview_locations_[timestamp].csv in
			<code class="path">/storage/emulated/0/Android/data/cz.hillview/files/GeoTrackingDumps/</code>
		</p>

		<button
			on:click={handleExport}
			data-testid="geo-tracking-export-button"
		>
			Export Location and Orientation Data
		</button>

		<p class="checkbox-row">
			<input
				type="checkbox"
				id="auto-export-checkbox"
				checked={autoExportEnabled}
				on:change={handleAutoExportChange}
				data-testid="geo-tracking-auto-export-checkbox"
			/>
			<label for="auto-export-checkbox">Automatically export on app start/exit</label>
		</p>

		<div class="section-divider"></div>
	{/if}
	<br/>
	<br/>

</StandardBody>

<style>
	.section-divider {
		height: 1px;
		padding: 0.5rem 0;
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

	code.path {
		display: block;
		background-color: #f3f4f6;
		padding: 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		word-break: break-all;
		overflow-wrap: break-word;
		margin-top: 0.5rem;
	}

	.checkbox-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.checkbox-row label {
		cursor: pointer;
	}
</style>
