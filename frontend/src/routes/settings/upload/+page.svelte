<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import UploadSettings from '$lib/components/UploadSettings.svelte';
	import PhotoPermissions from '$lib/components/PhotoPermissions.svelte';
	import { BROWSER } from '$lib/tauri';
</script>

<StandardHeaderWithAlert
	title="Photos & uploads"
	showMenuButton={true}
	fallbackHref="/settings"
/>

<StandardBody>
	{#if BROWSER}<PhotoPermissions />{/if}
	<UploadSettings />
</StandardBody>
