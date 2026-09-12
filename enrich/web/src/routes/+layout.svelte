<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { base } from '$app/paths';

	let { children } = $props();

	const links = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/photos', label: 'Photos' },
		{ href: '/annotations', label: 'Annotations' },
		{ href: '/geocode', label: 'Geocode' },
		{ href: '/calibration', label: 'Calibration' },
		{ href: '/matching', label: 'Matching' },
		{ href: '/transfer', label: 'Transfer' },
		{ href: '/triangulate', label: 'Triangulate' },
		{ href: '/terrain', label: 'Terrain' },
		{ href: '/recon', label: 'Recon' },
		{ href: '/graduation', label: 'Graduation' },
		{ href: '/runs', label: 'Runs' },
		{ href: '/sparql', label: 'SPARQL' }
	];

	// The list holds ROUTE paths; the base is applied at render. Both sides of the
	// comparison get it too, and both get their trailing slash trimmed, because a
	// prefixed root is served as "/prefix/" while base + "/" spells "/prefix".
	const trim = (p: string) => p.replace(/\/$/, '') || '/';

	function active(href: string): boolean {
		const here = trim(page.url.pathname);
		const full = trim(`${base}${href}`);
		return href === '/' ? here === full : here.startsWith(full);
	}
</script>

<nav class="top">
	<span class="brand">🛠 Enrichment Workbench</span>
	{#each links as l (l.href)}
		<a href="{base}{l.href}" class:active={active(l.href)}>{l.label}</a>
	{/each}
</nav>

<main>
	{@render children()}
</main>
