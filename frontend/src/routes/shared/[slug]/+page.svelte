<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { http } from '$lib/http';
	import Spinner from '$lib/components/Spinner.svelte';
	import ShareHead from '$lib/components/ShareHead.svelte';
	import type { PublicPhoto, PhotoAnnotation } from '$lib/photoDisplay';

	export let data: {
		target?: string;
		photo?: PublicPhoto | null;
		annotations?: PhotoAnnotation[];
	} | undefined = undefined;

	// Web SSR already resolved the link and rendered its card. SPA/Tauri builds
	// resolve it here instead. Both continue to exactly the saved map view.
	let error = '';

	onMount(async () => {
		try {
			if (data?.target) {
				await goto(data.target, { replaceState: true });
				return;
			}
			// params.slug types as string | undefined since the SvelteKit types
			// tightened; a missing slug is the same as a dead link.
			const slug = $page.params.slug;
			if (!slug) {
				error = 'This share link does not exist.';
				return;
			}
			const response = await http.get(`/shared/${encodeURIComponent(slug)}`);
			if (!response.ok) {
				error = response.status === 404 ? 'This share link does not exist.' : 'Failed to resolve share link.';
				return;
			}
			const resolved = await response.json();
			await goto(resolved.target, { replaceState: true });
		} catch (e) {
			console.error('🔗 Failed to resolve share link:', e);
			error = 'Failed to resolve share link.';
		}
	});
</script>

<ShareHead photo={data?.photo ?? null} annotations={data?.annotations ?? []} url={$page.url.href} />

<div class="shared-resolver" data-testid="shared-link-resolver">
	{#if error}
		<p class="error" data-testid="shared-link-error">{error}</p>
		<a href="/" data-testid="shared-link-home">Open the map</a>
	{:else}
		<Spinner />
		{#if data?.target}
			<a href={data.target} data-testid="shared-link-target">Open the shared view</a>
		{/if}
	{/if}
</div>

<style>
	.shared-resolver {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		min-height: 60vh;
	}

	.error {
		color: #6b7280;
	}

	.shared-resolver a {
		color: #3b82f6;
		text-decoration: underline;
	}
</style>
