<script lang="ts">
	import { page } from '$app/stores';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
</script>

<StandardHeaderWithAlert
	title="Photo not found"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	<div class="error-container" data-testid="photo-detail-error">
		<h1>{$page.status}</h1>
		<p>{$page.error?.message || 'Photo not found.'}</p>
		<p>
			Try browsing <a href="/bestof">Best of Hillview</a>,
			or <a href="/">go back to the map</a>.
		</p>
	</div>
</StandardBody>

<style>
	.error-container {
		text-align: center;
		padding: 4rem 2rem;
	}
	h1 {
		font-size: 3rem;
		margin: 0 0 1rem 0;
		color: #6b7280;
	}
	p {
		margin: 0.5rem 0;
		color: #4b5563;
	}
	a {
		color: #4f46e5;
		text-decoration: underline;
	}
</style>
