<script lang="ts">
	import PhotoHead from './PhotoHead.svelte';
	import JsonLd from './JsonLd.svelte';
	import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
	import {
		buildHeadTitle,
		buildHeadDescription,
		buildPhotoImageJsonLd,
		pickOgImage,
		type PublicPhoto,
		type PhotoAnnotation
	} from '$lib/photoDisplay';

	export let photo: PublicPhoto | null = null;
	export let annotations: PhotoAnnotation[] = [];
	export let url: string;

	$: photoImage = photo ? pickOgImage(photo) : null;
	$: image = photoImage?.url ? photoImage : {
		url: `${HILLVIEW_BASE_URL}/og-card.png`, width: 1200, height: 630
	};
</script>

<PhotoHead
	title={photo ? buildHeadTitle(photo, annotations) : 'Hillview - annotated panoramas'}
	description={photo
		? buildHeadDescription(photo, annotations)
		: "An open map of annotated panoramas and hilltop viewpoints — geotagged photos from places where cars can't go, labeled to help you make sense of the view."}
	ogType={photo ? 'article' : 'website'}
	ogUrl={url}
	ogImage={image}
	latitude={photo?.latitude ?? null}
	longitude={photo?.longitude ?? null}
	canonicalUrl={photo
		? `${HILLVIEW_BASE_URL}/photo/${encodeURIComponent(photo.uid)}`
		: `${HILLVIEW_BASE_URL}/`}
/>

{#if photo}
	<JsonLd data={buildPhotoImageJsonLd(photo, annotations)} />
{/if}
