<script lang="ts">
	/**
	 * The 3D world beside the map (recon ea05). The observer stands where the map's one location
	 * state says, facing its one bearing (docs/one-state.md); turning the view is a hand turn like the
	 * map's arrow drag (userTurn: the compass stops, car mode moves the mount offset), so the map's
	 * arrow follows and nothing automatic turns it back.
	 */
	import WorldScene from '$world/WorldScene.svelte';
	import { get } from 'svelte/store';
	import { bearingState, spatialState } from '$lib/mapState';
	import { userTurn } from '$lib/userTurn';
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
				userTurn(get(bearingState).bearing, look.bearing, 'world3d');
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
