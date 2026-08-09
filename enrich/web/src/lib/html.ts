/**
 * Escaping for the few sinks that take a markup STRING rather than a DOM node.
 *
 * Svelte's own `{}` interpolation is escaped, so components never need this.
 * Leaflet does need it: `bindTooltip`/`bindPopup`/`divIcon({html})` assign a
 * string straight to innerHTML (DivOverlay._updateContent), so a plain template
 * literal built from server data is an XSS sink. Candidate display names come
 * from OSM/Nominatim and annotation labels from arbitrary Hillview users —
 * neither is ours to trust.
 *
 * Use the `html` tagged template wherever markup is genuinely needed (the `<br>`
 * in a two-line tooltip); every `${}` is escaped, so the safe form is also the
 * shortest one. Where no markup is needed at all, `escapeHtml()` the value.
 */

const ENTITIES: Record<string, string> = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#39;'
};

export function escapeHtml(value: unknown): string {
	return String(value ?? '').replace(/[&<>"']/g, (c) => ENTITIES[c]);
}

export function html(strings: TemplateStringsArray, ...values: unknown[]): string {
	return strings.reduce(
		(out, chunk, i) => out + chunk + (i < values.length ? escapeHtml(values[i]) : ''),
		''
	);
}
