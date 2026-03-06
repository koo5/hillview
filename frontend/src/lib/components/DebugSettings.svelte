<script lang="ts">
	import {app} from '$lib/data.svelte';
	import SettingsSectionHeader from "$lib/components/SettingsSectionHeader.svelte";

</script>

<SettingsSectionHeader>Debug mode</SettingsSectionHeader>
<div class="setting-item">
	<label for="debug-mode">Enable Debug Mode</label>
	<input
		type="checkbox"
		id="debug-mode"
		bind:checked={$app.debug_enabled}
	/>
</div>

<style></style>
