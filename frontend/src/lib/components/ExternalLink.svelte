<script lang="ts">
	import { openExternalUrl } from '$lib/urlUtils';

	export let href: string;
	export let target: string = '_blank';
	export let rel: string = 'noopener noreferrer';

	async function handleClick(event: Event) {
		event.preventDefault();
		console.log('Opening external link:', href);
		await openExternalUrl(href);
	}
</script>

<a
	{href}
	{target}
	{rel}
	data-external-link="true"
	on:click={handleClick}
	{...$$restProps}
>
	<slot />
</a>

<style>
	a[data-external-link="true"] {
		position: relative;
	}

	a[data-external-link="true"]:after {
		content: '↗';
		font-size: 0.75em;
		margin-left: 2px;
		opacity: 0.7;
	}

	a[data-external-link="true"]:hover:after {
		opacity: 1;
	}
</style>