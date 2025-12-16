<script lang="ts">
    import {photoInFront, photosInRange, photoToLeft, photoToRight, photoUp, photoDown, updateBearing} from "$lib/mapState";
    import {turn_to_photo_to} from "$lib/data.svelte";
    import {swipe2d} from "$lib/actions/swipe2d";
    import Photo from "./Photo.svelte";
    import Spinner from "./Spinner.svelte";
    import {anySourceLoading} from "$lib/data.svelte.js";
    import type {PhotoData} from '$lib/sources';
	import PhotoMarkerIcon from "$lib/components/PhotoMarkerIcon.svelte";

    let clientWidth: number;
    let photoContainer: HTMLElement;
    let photosGrid: HTMLElement;

    // Reactive swipe options
    $: swipeOptions = {
        onSwipe: handleSwipe,
        snapThreshold: 50,
        enableVisualFeedback: true,
        transformTarget: photosGrid,
        dampingFactor: 1.0,
        canGoLeft: !!$photoToLeft,
        canGoRight: !!$photoToRight,
        canGoUp: !!$photoUp,
        canGoDown: !!$photoDown
    };

    // Update action when options change
    $: if (photoContainer && (photoContainer as any).__swipe2d_action) {
        (photoContainer as any).__swipe2d_action.update(swipeOptions);
    }

    function handleThumbnailClick(photo: PhotoData) {
        updateBearing(photo.bearing);
    }

    function handleSwipe(direction: 'left' | 'right' | 'up' | 'down') {
		console.log(`🢄Gallery: Detected swipe ${direction}`);
		// swiping left should go to photo on the right, etc.
		const directionMap = {
			'left': 'right',
			'right': 'left',
			'up': 'down',
			'down': 'up'
		};
		const mappedDirection = directionMap[direction];
        turn_to_photo_to(direction);
    }

    function handlePhotoInteraction() {
        // Reset swipe state when photo interactions (like zoom) occur
        if (photoContainer && (photoContainer as any).__swipe2d_action) {
            (photoContainer as any).__swipe2d_action.reset();
        }
    }

    // Log photo count changes
    /*
    $: if ($photosInRange) {
        console.log(`🢄Gallery: Displaying ${$photosInRange.length} photos in range`);
    }*/

	const cls = ['up', 'left', 'front', 'right', 'down'];
	$: keys = generate_keys([$photoUp, $photoToLeft, $photoInFront, $photoToRight, $photoDown]);
	function generate_keys(photos: (PhotoData | null)[]) {
		let keys = photos.map((photo, index) => photo ? photo.id : `empty-${index}`);
		// deduplicate
		const seen = new Set();
		for (let i = 0; i < keys.length; i++) {
			let key = keys[i];
			let count = 1;
			while (seen.has(key)) {
				key = `${keys[i]}-${count}`;
				count++;
			}
			seen.add(key);
			keys[i] = key;
		}
		console.log('🢄Gallery: Generated keys', keys);
		return keys;
	}

</script>

<div class="gallery-wrapper">
    <!--{#if $app.display_mode !== 'max'}-->
    <!--    <div class="thumbnails-top">-->
    <!--        {#each $photosInRange as photo}-->
    <!--            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>-->
    <!--                {#if photo.is_device_photo}-->
    <!--                    <img src={getDevicePhotoUrl(photo.url)} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>-->
    <!--                {:else if photo.sizes && photo.sizes[50]}-->
    <!--                    <img src={photo.sizes[50].url} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>-->
    <!--                {/if}-->
    <!--            </div>-->
    <!--        {/each}-->
    <!--    </div>-->
    <!--{/if}-->

    <div bind:clientWidth bind:this={photoContainer} class="photo-container" use:swipe2d={swipeOptions}>
        <!-- Navigation buttons on sides -->
        {#if $photoToLeft}
            <button class="nav-button nav-left" on:click={() => handleSwipe('left')} title="Previous photo">
                <PhotoMarkerIcon bearing={-90} />
            </button>
        {/if}

        {#if $photoToRight}
            <button class="nav-button nav-right" on:click={() => handleSwipe('right')} title="Next photo">
                <PhotoMarkerIcon bearing={90} />
            </button>
        {/if}

        {#if $photoUp}
            <button class="nav-button nav-up" on:click={() => handleSwipe('up')} title="Photo above">
                ↑
            </button>
        {/if}

        {#if $photoDown}
            <button class="nav-button nav-down" on:click={() => handleSwipe('down')} title="Photo below">
                ↓
            </button>
        {/if}

        <div class="photos-grid" bind:this={photosGrid}>

			{#if !$photoInFront}
				<div class="no-photo">
					{#if $anySourceLoading}
						<div class="loading-container">
							<Spinner show={true} color="#ffffff" />
							<p>Loading photos...</p>
						</div>
					{:else}
						<p>No photos in range</p>
					{/if}
				</div>
			{/if}

			{#each [$photoUp, $photoToLeft, $photoInFront, $photoToRight, $photoDown] as photo, index (keys[index])}
				<div class="photo-slot {cls[index]}">
					{#if photo}
						<Photo photo={photo} className="{cls[index]}" {clientWidth} onInteraction={handlePhotoInteraction}/>
					{/if}
				</div>
			{/each}

        </div>
    </div>

    <!--{#if $app.display_mode !== 'max'}-->
    <!--    <div class="thumbnails-bottom">-->
    <!--        {#each $photosInRange as photo}-->
    <!--            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>-->
    <!--                {#if photo.is_device_photo}-->
    <!--                    <img src={getDevicePhotoUrl(photo.url)} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>-->
    <!--                {:else if photo.sizes && photo.sizes[50]}-->
    <!--                    <img src={photo.sizes[50].url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>-->
    <!--                {/if}-->
    <!--            </div>-->
    <!--        {/each}-->
    <!--    </div>-->
    <!--{/if}-->


</div>


<style>
    .gallery-wrapper {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        max-height: 100%;
        /*background: linear-gradient(135deg, #388E3C, #689F38);*/
		background: linear-gradient(135deg, #000000, #388E3C);
    }

    /*.thumbnails-top, .thumbnails-bottom {*/
    /*    display: flex;*/
    /*    overflow-x: auto;*/
    /*    padding: 1px;*/
    /*    background-color: rgba(0, 0, 0, 0.5);*/
    /*    height: 50px;*/
    /*    z-index: 30000;*/
    /*}*/

    /*.thumbnails-bottom {*/
    /*    flex-direction: row-reverse;*/
    /*}*/

    /*.thumbnail {*/
    /*    flex: 0 0 auto;*/
    /*    margin: 0 5px;*/
    /*    cursor: pointer;*/
    /*    transition: transform 0.2s;*/
    /*}*/

    /*.thumbnail:hover {*/
    /*    transform: scale(1.1);*/
    /*}*/

    /*.thumbnail img {*/
    /*    height: 50px;*/
    /*    width: 50px;*/
    /*    object-fit: cover;*/
    /*    border: 2px solid;*/
    /*    border-radius: 4px;*/
    /*}*/

    /*ul {*/
    /*    margin: 0.3em;*/
    /*}*/

    /*.no-photo {*/
    /*    */
    /*}*/

    .photo-container {
        position: relative;
        flex: 1;
        width: 100%;
        overflow: hidden;
    }

    .photos-grid {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        grid-template-rows: 1fr 1fr 1fr;
        width: 300%;
        height: 300%;
        position: relative;
        left: -100%;
        top: -100%;
        transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
        box-sizing: border-box;
    }

    .photo-slot {
        position: relative;
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        max-width: 100%;
        max-height: 100%;
    }

    .photo-slot.up {
        grid-column: 2;
        grid-row: 1;
    }

    .photo-slot.left {
        grid-column: 1;
        grid-row: 2;
    }

    .photo-slot.front {
        grid-column: 2;
        grid-row: 2;
    }

    .photo-slot.right {
        grid-column: 3;
        grid-row: 2;
    }

    .photo-slot.down {
        grid-column: 2;
        grid-row: 3;
    }

    .no-photo {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        color: #ffffff;
    }

    .loading-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }

    .loading-container p {
        margin: 0;
        font-size: 1rem;
        opacity: 0.8;
    }

    .nav-button {
        position: absolute;
        background: rgba(0, 0, 0, 0.6);
        border: none;
        color: white;
        cursor: pointer;
        font-size: 1.5rem;
        font-weight: bold;
        border-radius: 50%;
        width: 48px;
        height: 48px;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10;
        opacity: 0.7;
        transition: opacity 0.3s ease, background 0.3s ease;
        user-select: none;
    }

    .nav-button:hover {
        opacity: 1;
        background: rgba(0, 0, 0, 0.8);
    }

    .nav-left {
        left: 16px;
        top: 50%;
        transform: translateY(-50%);
    }

    .nav-right {
        right: 16px;
        top: 50%;
        transform: translateY(-50%);
    }

    .nav-up {
        top: 16px;
        left: 50%;
        transform: translateX(-50%);
    }

    .nav-down {
        bottom: 16px;
        left: 50%;
        transform: translateX(-50%);
    }


</style>
