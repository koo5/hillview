<script lang="ts">
	export let title: string;
	export let description: string;
	export let ogType: 'article' | 'website' = 'article';
	export let ogUrl: string | null = null;
	export let ogImage: { url: string; width?: number; height?: number } | null = null;
	export let latitude: number | null = null;
	export let longitude: number | null = null;
	export let canonicalUrl: string | null = null;
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />

	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:type" content={ogType} />
	{#if ogUrl}
		<meta property="og:url" content={ogUrl} />
	{/if}
	{#if ogImage}
		<meta property="og:image" content={ogImage.url} />
		{#if ogImage.width}
			<meta property="og:image:width" content={ogImage.width.toString()} />
		{/if}
		{#if ogImage.height}
			<meta property="og:image:height" content={ogImage.height.toString()} />
		{/if}
	{/if}

	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	{#if ogImage}
		<meta name="twitter:image" content={ogImage.url} />
	{/if}

	{#if latitude != null && longitude != null}
		<meta property="place:location:latitude" content={latitude.toString()} />
		<meta property="place:location:longitude" content={longitude.toString()} />
	{/if}

	{#if canonicalUrl}
		<link rel="canonical" href={canonicalUrl} />
	{/if}
</svelte:head>
