<script lang="ts">
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import SettingsComponent from '$lib/components/CameraSettings.svelte';
	import UploadSettingsComponent from '$lib/components/UploadSettings.svelte';
	import type { Alert } from '$lib/alertSystem.svelte';
	import {Database} from "lucide-svelte";

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

		<div class="section-divider"></div>
		<h2>Sources Settings</h2>
           <a href="/settings/sources" data-testid="sources-menu-link">
                <Database size={18}/>
                Sources
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
		margin: 2rem 0;
	}
</style>
