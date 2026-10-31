<script lang="ts">
	/**
	 * The 3D world beside the map (recon ea05). The observer stands where the map's one location
	 * state says, facing its one bearing (docs/one-state.md); turning the view writes the bearing
	 * back through the same funnel as every other writer, so the map's arrow follows.
	 */
	import WorldScene from '$world/WorldScene.svelte';
	import { bearingState, spatialState, updateBearing } from '$lib/mapState';
	import { earthUrl } from '$lib/world';

	let pitch = $state(-5);
	let eyeM = $state(2);
</script>

<div class="world-pane" data-testid="world-pane">
	{#if earthUrl}
		<WorldScene
			{earthUrl}
			lat={$spatialState.center.lat}
			lon={$spatialState.center.lng}
			bearing={$bearingState.bearing}
			{pitch}
			{eyeM}
			onlook={(look) => {
				pitch = look.pitch;
				updateBearing(look.bearing, 'world3d');
			}}
			oneye={(m) => (eyeM = m)}
			testid="world-scene"
		/>
	{/if}
</div>

<style>
	.world-pane {
		width: 100%;
		height: 100%;
	}
</style>
