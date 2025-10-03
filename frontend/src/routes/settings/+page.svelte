<script lang="ts">
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import SettingsComponent from '$lib/components/Settings.svelte';
	import UploadSettingsComponent from '$lib/components/UploadSettings.svelte';

	let alertMessage = '';
	let alertType: 'success' | 'warning' | 'error' | 'info' = 'info';

	function showAlert(message: string, type: 'success' | 'warning' | 'error' | 'info' = 'info') {
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
		<!-- General Settings -->
		<SettingsComponent
			onSaveSuccess={(message) => showAlert(message, 'success')}
			onSaveError={(message) => showAlert(message, 'error')}
		/>

		<!-- Upload Settings -->
		<div class="section-divider"></div>
		<UploadSettingsComponent
			onSaveSuccess={(message) => showAlert(message, 'success')}
			onSaveError={(message) => showAlert(message, 'error')}
		/>
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
		margin: 2rem 0;
	}
</style>