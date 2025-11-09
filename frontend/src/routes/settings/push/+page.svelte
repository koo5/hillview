<svelte:head>
	<title>Push Messaging Settings - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from '../../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../../components/StandardBody.svelte';
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