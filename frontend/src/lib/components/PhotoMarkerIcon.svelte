<script>
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
		width: px;
		height: 32px;
	}
</style>
