<script lang="ts">
	import { onDestroy } from 'svelte';
	import { MapPin, Search } from 'lucide-svelte';
	import { searchPlaces, type PlaceResult } from '$lib/placesApi';
	import { parseCoordinateQuery } from '$lib/utils/coordParser';
	import PlaceAttribution from './PlaceAttribution.svelte';

	export let onSelect: (place: PlaceResult) => void;
	export let canSelect = true;
	let query = '';
	let results: PlaceResult[] = [];
	let loading = false;
	let searched = false;
	let error = '';
	let selectedId: string | null = null;
	let pending: AbortController | null = null;

	function reset() {
		pending?.abort();
		pending = null;
		loading = false;
		searched = false;
		results = [];
		error = '';
		selectedId = null;
	}

	async function search() {
		reset();
		if (query.trim().length < 2) return;
		const coords = parseCoordinateQuery(query);
		if (coords) {
			results = [{
				id: 'coordinates', name: 'Coordinates',
				display_name: `${coords.lat.toFixed(7)}, ${coords.lon.toFixed(7)}`,
				lat: coords.lat, lon: coords.lon, bounds: null
			}];
			searched = true;
			return;
		}
		const request = new AbortController();
		pending = request;
		loading = true;
		try {
			const places = await searchPlaces(query, request.signal);
			if (request.signal.aborted) return;
			results = places;
			searched = true;
		} catch (e) {
			if (request.signal.aborted) return;
			error = e instanceof Error ? e.message : 'Place search failed. Please try again.';
		} finally {
			if (pending === request) {
				loading = false;
				pending = null;
			}
		}
	}

	onDestroy(() => pending?.abort());
</script>

<section class="search-pane" data-testid="search-pane" aria-label="Place search">
	<h1>Search places</h1>
	<form role="search" on:submit|preventDefault={search}>
		<label for="place-search">Place, address, or coordinates</label>
		<div class="search-box">
			<input id="place-search" type="search" bind:value={query} on:input={reset}
				placeholder="Prague or 50.0875, 14.4213" maxlength="200" autocomplete="off"
				data-testid="place-search-input" />
			<button type="submit" disabled={query.trim().length < 2 || loading}
				aria-label="Search places" data-testid="place-search-submit"><Search size={20} /></button>
		</div>
	</form>
	<div class="status" role="status" aria-live="polite">
		{#if loading}
			<p data-testid="place-search-loading">Searching…</p>
		{:else if error}
			<p class="error" data-testid="place-search-error">{error}</p>
		{:else if searched && results.length === 0}
			<p data-testid="place-search-empty">No places found. Try a different name or add a nearby town.</p>
		{:else if searched}
			<p>{results.length} {results.length === 1 ? 'result' : 'results'} — select one to move the map.</p>
		{:else}
			<p>Search for a place, then select a result to explore it on the map.</p>
		{/if}
	</div>
	{#if results.length > 0}
		<ul data-testid="place-search-results">
			{#each results as place}
				<li>
					<button type="button" class:selected={selectedId === place.id}
						aria-pressed={selectedId === place.id} data-testid="place-search-result"
						disabled={!canSelect}
						on:click={() => { selectedId = place.id; onSelect(place); }}>
						<MapPin size={20} />
						<span><strong>{place.name}</strong><small>{place.display_name}</small></span>
					</button>
				</li>
			{/each}
		</ul>
		{#if results.some(place => place.id !== 'coordinates')}
			<PlaceAttribution label="Search results" />
		{/if}
	{/if}
</section>

<style>
	.search-pane {
		min-height: 100%;
		padding: calc(60px + var(--safe-area-inset-top, 10px)) 1rem 1rem;
		padding-left: max(1rem, var(--safe-area-inset-left, 10px));
		color: #eaf0f6;
		background: linear-gradient(135deg, #111820, #20374c);
	}
	h1 { margin: 0 0 1rem; font-size: 1.3rem; }
	label { display: block; margin-bottom: 0.4rem; font-size: 0.9rem; }
	.search-box { display: flex; gap: 0.5rem; }
	input {
		flex: 1; min-width: 0; padding: 0.75rem; border: 1px solid #7c8d9d;
		border-radius: 0.5rem; background: #fff; color: #17212b; font-size: 1rem;
	}
	.search-box button {
		display: grid; place-items: center; min-width: 44px; border: 0;
		border-radius: 0.5rem; background: #4a90e2; color: #fff; cursor: pointer;
	}
	.search-box button:disabled { opacity: 0.5; cursor: default; }
	.status { font-size: 0.9rem; color: #b9c9d8; }
	.error { color: #ffb6b6; }
	ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
	li button {
		display: flex; align-items: flex-start; gap: 0.6rem; width: 100%; padding: 0.8rem;
		border: 1px solid #566b7e; border-radius: 0.5rem; background: #ffffff0a;
		color: inherit; text-align: left; cursor: pointer;
	}
	li button:hover, li button.selected { background: #4a90e22b; border-color: #69adff; }
	li button:disabled { opacity: 0.5; cursor: default; }
	li button :global(svg) { flex-shrink: 0; margin-top: 0.1rem; }
	strong, small { display: block; overflow-wrap: anywhere; }
	small { margin-top: 0.3rem; color: #b9c9d8; line-height: 1.4; }
	button:focus-visible, input:focus-visible { outline: 2px solid #88c5ff; outline-offset: 2px; }
</style>
