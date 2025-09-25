<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Spinner from '../../components/Spinner.svelte';

	export let hasMore: boolean = false;
	export let loading: boolean = false;
	export let onLoadMore: () => void;
	export let rootMargin: string = '100px';

	let buttonElement: HTMLElement;
	let intersectionObserver: IntersectionObserver | null = null;

	onMount(() => {
		setupIntersectionObserver();
	});

	onDestroy(() => {
		if (intersectionObserver) {
			intersectionObserver.disconnect();
		}
	});

	function setupIntersectionObserver() {
		if (typeof window !== 'undefined' && 'IntersectionObserver' in window) {
			intersectionObserver = new IntersectionObserver(
				(entries) => {
					entries.forEach((entry) => {
						if (entry.isIntersecting && hasMore && !loading) {
							onLoadMore();
						}
					});
				},
				{
					rootMargin
				}
			);
		}
	}

	$: if (intersectionObserver && buttonElement) {
		intersectionObserver.observe(buttonElement);
	}

	function handleClick() {
		if (hasMore && !loading) {
			onLoadMore();
		}
	}
</script>

{#if hasMore}
	<div class="load-more-container">
		<button
			bind:this={buttonElement}
			class="load-more-button"
			on:click={handleClick}
			disabled={loading}
			data-testid="load-more-button"
		>
			{#if loading}
				<Spinner />
				Loading more...
			{:else}
				Load More Photos
			{/if}
		</button>
	</div>
{/if}

<style>
	.load-more-container {
		display: flex;
		justify-content: center;
		margin-top: 2rem;
		padding: 1rem;
	}

	.load-more-button {
		background: #4a90e2;
		color: white;
		border: none;
		padding: 0.75rem 2rem;
		border-radius: 8px;
		font-size: 1rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 160px;
		justify-content: center;
	}

	.load-more-button:hover:not(:disabled) {
		background: #357abd;
		transform: translateY(-1px);
	}

	.load-more-button:disabled {
		cursor: not-allowed;
		opacity: 0.7;
	}
</style>