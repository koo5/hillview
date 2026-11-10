<script lang="ts">
	/**
	 * The 3D world beside the map (recon ea05). The observer stands where the map's one location
	 * state says, facing its one bearing (docs/one-state.md); turning the view is a hand turn like the
	 * map's arrow drag (userTurn: the compass stops, car mode moves the mount offset), so the map's
	 * arrow follows and nothing automatic turns it back. Flying in it is a hand move like a map pan (userMove: GPS
	 * following goes to the background first), so the map follows the flight and the next fix does not land it.
	 */
	import WorldScene from '$world/WorldScene.svelte';
	import { get } from 'svelte/store';
	import { bearingState, spatialState } from '$lib/mapState';
	import { userTurn } from '$lib/userTurn';
	import { userMove } from '$lib/userMove';
	import { atlasChannels, atlasUrl, earthChannel, earthUrl } from '$lib/world';

	let pitch = $state(-5);
	/** the first view stands 20 m over the ground, not at a standing 2 m (the operator, 11-10) */
	let eyeM = $state(20);
	/** a photo picked on the map moved the observer to its position (spatialState.photoUid): it stands there at a
	 * photographer's eye height, from whatever height it had -- flown, kept from a pan, raised by the stick or the
	 * first view's (the operator, 11-10). Only a new pick: the one the app opened on does not lower the first view */
	const PHOTO_EYE_M = 2;
	const pickedPhoto = $derived($spatialState.photoUid);
	let seenPhoto = get(spatialState).photoUid;
	$effect(() => {
		const uid = pickedPhoto;
		if (uid && uid !== seenPhoto) eyeM = PHOTO_EYE_M;
		seenPhoto = uid;
	});
	/** one map pixel on the ground at the map's zoom: the map rounds its centre to its pixels, so a flight's own
	 * position can come back this far off (WorldScene's echo test) */
	const mapPixelM = $derived(
		(40_075_016.686 * Math.cos(($spatialState.center.lat * Math.PI) / 180)) / (256 * 2 ** $spatialState.zoom)
	);
</script>

<div class="world-pane" data-testid="world-pane">
	{#if earthUrl}
		<WorldScene
			{earthUrl}
			channel={earthChannel}
			lat={$spatialState.center.lat}
			lon={$spatialState.center.lng}
			bearing={$bearingState.bearing}
			{pitch}
			{eyeM}
			landAtEye={!!$spatialState.photoUid}
			onlook={(look) => {
				pitch = look.pitch;
				userTurn(get(bearingState).bearing, look.bearing, 'world3d');
			}}
			oneye={(m) => (eyeM = m)}
			onmove={(at) => userMove({ lat: at.lat, lng: at.lon })}
			locationPrecisionM={mapPixelM}
			atlasUrl={atlasUrl ?? undefined}
			{atlasChannels}
			testid="world-scene"
		/>
	{/if}
</div>

<style>
	/* the app's top buttons sit over the pane's top edge: the scene's loading line and layers button start below them */
	.world-pane {
		width: 100%;
		height: 100%;
		--world-scene-inset-top: 60px;
	}
	/* the split's divider (22 px, centred on the split) covers this pane's bottom edge in portrait and its right
	   edge in landscape: the scene's credit line moves clear of it */
	@media (orientation: portrait) {
		.world-pane {
			--world-scene-credits-bottom: 12px;
		}
	}
	@media (orientation: landscape) {
		.world-pane {
			--world-scene-credits-right: 12px;
		}
	}
</style>
