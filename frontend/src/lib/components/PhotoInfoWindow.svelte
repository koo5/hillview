<script lang="ts">
	import type { PhotoData } from '$lib/types/photoTypes';
	import { X } from 'lucide-svelte';
	import { showPhotoInfoWindow } from '$lib/data.svelte';
	import {
		getPhotoSourceId,
		getPhotoSourceName,
		getUserName,
		getLicenseLabel,
		formatCapturedAt
	} from '$lib/photoUtils';
	import {
		fetchExif,
		getCachedExif,
		formatFocalLength,
		formatAperture,
		formatIso,
		formatShutter,
		formatCamera,
		type PhotoExif
	} from '$lib/photoExif';

	export let photo: PhotoData | null = null;
	// 'map' = corner of the map pane; 'zoom' = corner of the full-screen zoom view.
	export let variant: 'map' | 'zoom' = 'map';

	$: uid = photo?.uid ?? null;
	$: isHillview = getPhotoSourceId(photo) === 'hillview';

	// Curated camera/lens EXIF is only served for hillview photos, and only via a
	// per-photo fetch (cached). Base metadata below comes straight off the local
	// photo object, so the window is useful immediately while EXIF resolves.
	let exif: PhotoExif | null = null;
	let exifUid: string | null = null;
	let exifLoading = false;

	function loadExif(u: string | null, hillview: boolean) {
		if (u === exifUid) return;
		exifUid = u;
		exif = null;
		exifLoading = false;
		if (!u || !hillview) return;
		const cached = getCachedExif(u);
		if (cached !== undefined) {
			exif = cached;
			return;
		}
		exifLoading = true;
		fetchExif(u).then(result => {
			if (u !== exifUid) return; // focused photo changed while we waited
			exif = result;
			exifLoading = false;
		});
	}
	$: loadExif(uid, isHillview);

	// EXIF rows (precise values; see photoExif formatters).
	$: cameraStr = exif ? formatCamera(exif.make, exif.model) : null;
	$: lensStr = exif?.lens ?? null;
	$: focalStr = exif ? formatFocalLength(exif) : null;
	$: apertureStr = exif ? formatAperture(exif.f_number) : null;
	$: shutterStr = exif ? formatShutter(exif.exposure_time) : null;
	$: isoStr = exif ? formatIso(exif.iso) : null;
	$: hasCameraExif = !!(cameraStr || lensStr || focalStr || apertureStr || shutterStr || isoStr);

	// Base metadata rows. Precision matches the DebugOverlay conventions.
	$: capturedStr = formatCapturedAt(photo);
	$: coordStr = photo?.coord ? `${photo.coord.lat?.toFixed(6)}, ${photo.coord.lng?.toFixed(6)}` : null;
	$: bearingStr = photo?.bearing != null ? `${photo.bearing.toFixed(1)}°` : null;
	$: altitudeStr = photo?.altitude != null ? `${photo.altitude.toFixed(0)} m` : null;
	$: dims = photo?.sizes?.full?.width && photo?.sizes?.full?.height
		? `${photo.sizes.full.width} × ${photo.sizes.full.height}`
		: null;
	$: sourceName = getPhotoSourceName(photo) ?? getPhotoSourceId(photo) ?? null;
	$: creator = getUserName(photo);
	$: licenseStr = getLicenseLabel(photo);
	$: filename = photo?.filename ?? null;
</script>

<!-- Listeners only stop pointer/scroll events from reaching the map underneath. -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
	class="pinfo pinfo--{variant}"
	data-testid="photo-info-window"
	role="region"
	aria-label="Photo information"
	on:mousedown|stopPropagation
	on:touchstart|stopPropagation
	on:wheel|stopPropagation
>
	<div class="pinfo-header">
		<span class="pinfo-title">Photo info</span>
		<button
			type="button"
			class="pinfo-close"
			data-testid="photo-info-close"
			aria-label="Close info window"
			on:click={() => showPhotoInfoWindow.set(false)}
		>
			<X size={16} aria-hidden="true" />
		</button>
	</div>

	{#if !photo}
		<div class="pinfo-empty" data-testid="photo-info-empty">No photo in front</div>
	{:else}
		<dl class="pinfo-list">
			{#if cameraStr}<dt>Camera</dt><dd>{cameraStr}</dd>{/if}
			{#if lensStr}<dt>Lens</dt><dd>{lensStr}</dd>{/if}
			{#if focalStr}<dt>Focal length</dt><dd>{focalStr}</dd>{/if}
			{#if apertureStr}<dt>Aperture</dt><dd>{apertureStr}</dd>{/if}
			{#if shutterStr}<dt>Shutter</dt><dd>{shutterStr}</dd>{/if}
			{#if isoStr}<dt>ISO</dt><dd>{isoStr}</dd>{/if}

			{#if isHillview && !hasCameraExif}
				<dd class="pinfo-note">{exifLoading ? 'Loading EXIF…' : 'No camera EXIF'}</dd>
			{/if}

			{#if capturedStr}<dt>Captured</dt><dd>{capturedStr}</dd>{/if}
			{#if coordStr}<dt>Coords</dt><dd>{coordStr}</dd>{/if}
			{#if bearingStr}<dt>Bearing</dt><dd>{bearingStr}</dd>{/if}
			{#if altitudeStr}<dt>Altitude</dt><dd>{altitudeStr}</dd>{/if}
			{#if dims}<dt>Dimensions</dt><dd>{dims}</dd>{/if}
			{#if sourceName}<dt>Source</dt><dd>{sourceName}</dd>{/if}
			{#if creator}<dt>By</dt><dd>{creator}</dd>{/if}
			{#if licenseStr}<dt>License</dt><dd>{licenseStr}</dd>{/if}
			{#if filename}<dt>File</dt><dd class="pinfo-file">{filename}</dd>{/if}
		</dl>
	{/if}
</div>

<style>
	.pinfo {
		position: absolute;
		max-width: 280px;
		max-height: 60%;
		overflow-y: auto;
		background: rgba(0, 0, 0, 0.72);
		color: #fff;
		border-radius: 10px;
		padding: 8px 10px 10px;
		font-size: 0.75rem;
		line-height: 1.35;
		box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
		user-select: text;
	}

	/* Sit above the map's own overlay controls (z-index ladder tops out ~30001). */
	.pinfo--map {
		z-index: 30050;
		top: 8px;
		left: 8px;
	}

	/* Inside the zoom overlay's stacking context (close/toolbar sit at z-index 10). */
	.pinfo--zoom {
		z-index: 12;
		bottom: calc(12px + var(--safe-area-inset-bottom, 0px));
		left: calc(12px + var(--safe-area-inset-left, 0px));
	}

	.pinfo-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 6px;
	}

	.pinfo-title {
		font-weight: 600;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		opacity: 0.8;
	}

	.pinfo-close {
		display: flex;
		align-items: center;
		justify-content: center;
		flex: none;
		width: 24px;
		height: 24px;
		padding: 0;
		border: none;
		border-radius: 6px;
		background: rgba(255, 255, 255, 0.14);
		color: #fff;
		cursor: pointer;
	}

	.pinfo-close:hover {
		background: rgba(255, 255, 255, 0.28);
	}

	.pinfo-list {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 2px 10px;
		margin: 0;
	}

	.pinfo-list dt {
		opacity: 0.6;
		white-space: nowrap;
	}

	.pinfo-list dd {
		margin: 0;
		overflow-wrap: anywhere;
	}

	.pinfo-note {
		grid-column: 1 / -1;
		opacity: 0.55;
		font-style: italic;
	}

	.pinfo-file {
		font-size: 0.7rem;
		opacity: 0.85;
	}

	.pinfo-empty {
		opacity: 0.7;
	}
</style>
