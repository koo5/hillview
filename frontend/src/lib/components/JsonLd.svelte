<script lang="ts">
	import { serializeJsonLd } from '$lib/jsonld';

	// Renders a schema.org structured-data block as JSON-LD.
	//
	// Svelte can't render a reactive <script> tag directly (it hoists any
	// <script> at compile time), so JSON-LD has to go through {@html}.
	// serializeJsonLd escapes '<', which is what makes that safe — see its docs.
	export let data: Record<string, unknown> | null = null;

	$: html = data
		? `<script type="application/ld+json">${serializeJsonLd(data)}<\/script>`
		: '';
</script>

<svelte:head>
	{#if data}{@html html}{/if}
</svelte:head>
