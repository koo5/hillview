<script lang="ts">
	import { constructShareUrl, openExternalUrl } from '$lib/urlUtils';

	export let data;

	function getPhotoUrl(photo: any): string {
		return photo.sizes?.['320']?.url || '';
	}

	function openPhoto(photo: any) {
		openExternalUrl(constructShareUrl(photo));
	}
</script>

<svelte:head>
	<title>Photos - Hillview</title>
</svelte:head>

<div class="tile-grid">
	{#each data.photos as photo}
		{#if photo.latitude && photo.longitude}
			<button class="tile" on:click={() => openPhoto(photo)} data-testid="photo-tile">
				<img src={getPhotoUrl(photo)} alt="" loading="lazy" />
			</button>
		{/if}
	{/each}
</div>

<style>
	.tile-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 4px;
		padding: 4px;
	}

	.tile {
		aspect-ratio: 1;
		overflow: hidden;
		display: block;
		border: none;
		padding: 0;
		cursor: pointer;
		background: #f0f0f0;
	}

	.tile img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform 0.2s ease;
	}

	.tile:hover img {
		transform: scale(1.05);
	}
</style>
