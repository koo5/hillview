<script lang="ts">
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import SettingsComponent from '$lib/components/Settings.svelte';

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
		<SettingsComponent
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

</style>