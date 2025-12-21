<script>

	/* PhotoMarkerIcon is used by map and gallery to indicate going to next/previous photo either clockwise or counter-clockwise */

	import { optimizedMarkerSystem } from '$lib/optimizedMarkers';

	export let bearing = 0;

	let html;
	$: html = optimizedMarkerSystem.markerDivsHtml(bearing, '#0c0');

</script>

<div class="photo-marker-icon" >
	{@html html}
</div>

<style>
	.photo-marker-icon {
		width: 24px;
		height: 32px;
	}
</style>
