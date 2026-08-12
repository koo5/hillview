<script lang="ts">
	/**
	 * ODbL credit for reverse-geocoded place names (backfill_places.py → Nominatim,
	 * which returns "Data © OpenStreetMap contributors, ODbL 1.0" with every
	 * response). Required wherever those names are shown.
	 *
	 * Deliberately its own line rather than borrowing the Leaflet map's credit:
	 * these pages have no map, so there is nothing to borrow — the same reason
	 * the terrain pane carries its own peaks credit (docs/terrain-data-licensing.md).
	 *
	 * Render it only when a place name is actually on screen (titleUsesPlace);
	 * crediting OSM on a page that shows none of its data is noise, not
	 * compliance.
	 *
	 * `label` scopes the claim to what is really OSM-derived. On a list where
	 * only part of the headings fall back to a geocoded place — the rest being
	 * titles their authors wrote — "Place names ©" would sweep those in too, so
	 * callers pass "Some place names". Singular on a photo page.
	 */
	export let label: string = 'Place names';
</script>

<p class="place-attribution" data-testid="place-attribution">
	{label} ©
	<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer"
		>OpenStreetMap contributors</a
	>, ODbL
</p>

<style>
	.place-attribution {
		margin: 0;
		padding: 0.75rem 0 1.5rem;
		text-align: center;
		font-size: 0.75rem;
		color: #9aa2aa;
	}

	.place-attribution a {
		color: inherit;
		text-decoration: underline;
	}
</style>
