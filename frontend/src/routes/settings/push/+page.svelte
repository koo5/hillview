<svelte:head>
	<title>Push Messaging Settings - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import PushSettings from '$lib/components/PushSettings.svelte';
</script>

<StandardHeaderWithAlert
	title="Push Messaging"
	showMenuButton={true}
	fallbackHref="/settings"
/>

<StandardBody>
	<PushSettings />
</StandardBody>
