<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import UploadSettings from '$lib/components/UploadSettings.svelte';
</script>

<StandardHeaderWithAlert
	title="Automatic Upload"
	showMenuButton={true}
	fallbackHref="/settings"
/>

<StandardBody>
	<UploadSettings />
</StandardBody>
