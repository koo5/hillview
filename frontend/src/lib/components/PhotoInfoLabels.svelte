<script lang="ts">
	import type {PhotoData} from '$lib/sources';
	import type {AnnotationData} from '$lib/annotationApi';

	export let photo: PhotoData | null = null;
	export let annotations: AnnotationData[] = [];
</script>

{#if photo?.description}
	<div class="photo-description" data-testid="photo-description"
		on:mousedown|stopPropagation on:touchstart|stopPropagation>
		{photo.description}
	</div>
	{:else if photo?.filename}
	<div class="photo-description" data-testid="photo-filename"
		on:mousedown|stopPropagation on:touchstart|stopPropagation>
		{photo.filename}
	</div>
{/if}

{#if annotations.length > 0}
	<div class="annotation-indicator" data-testid="annotation-indicator">
		{annotations.length} annotation{annotations.length !== 1 ? 's' : ''}
	</div>
{/if}

<style>
	.photo-description {
		position: absolute;
		bottom: 24px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0, 0, 0, 0.6);
		color: #fff;
		font-size: 0.75rem;
		padding: 2px 8px;
		border-radius: 8px;
		z-index: 10;
		max-width: 80%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		user-select: text;
		cursor: text;
	}

	.annotation-indicator {
		position: absolute;
		bottom: 4px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0, 0, 0, 0.6);
		color: #fff;
		font-size: 0.75rem;
		padding: 2px 8px;
		border-radius: 8px;
		pointer-events: none;
		z-index: 10;
		white-space: nowrap;
	}
</style>
