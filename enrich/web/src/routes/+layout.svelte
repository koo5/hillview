<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';

	let { children } = $props();

	const links = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/photos', label: 'Photos' },
		{ href: '/annotations', label: 'Annotations' },
		{ href: '/geocode', label: 'Geocode' },
		{ href: '/calibration', label: 'Calibration' },
		{ href: '/matching', label: 'Matching' },
		{ href: '/triangulate', label: 'Triangulate' },
		{ href: '/graduation', label: 'Graduation' },
		{ href: '/runs', label: 'Runs' },
		{ href: '/sparql', label: 'SPARQL' }
	];

	function active(href: string): boolean {
		return href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
	}
</script>

<nav class="top">
	<span class="brand">🛠 Enrichment Workbench</span>
	{#each links as l (l.href)}
		<a href={l.href} class:active={active(l.href)}>{l.label}</a>
	{/each}
</nav>

<main>
	{@render children()}
</main>
