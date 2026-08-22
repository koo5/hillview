<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { http } from '$lib/http';
	import Spinner from '$lib/components/Spinner.svelte';

	// On the web build this page never renders: +page.server.ts.web resolves the
	// slug and 301s before hydration. This client-side path serves the SPA/Tauri
	// builds, where the route is reachable e.g. via a tapped share link.
	let error = '';

	onMount(async () => {
		try {
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
			const data = await response.json();
			await goto(data.target, { replaceState: true });
		} catch (e) {
			console.error('🔗 Failed to resolve share link:', e);
			error = 'Failed to resolve share link.';
		}
	});
</script>

<svelte:head>
	<title>Shared photo - Hillview</title>
</svelte:head>

<div class="shared-resolver" data-testid="shared-link-resolver">
	{#if error}
		<p class="error" data-testid="shared-link-error">{error}</p>
		<a href="/" data-testid="shared-link-home">Open the map</a>
	{:else}
		<Spinner />
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
