<script lang="ts">
	import {app} from '$lib/data.svelte';

</script>

<h2>Debug mode</h2>
<div class="setting-item">
	<label for="debug-mode">Enable Debug Mode</label>
	<input
		type="checkbox"
		id="debug-mode"
		bind:checked={$app.debug_enabled}
	/>
</div>
