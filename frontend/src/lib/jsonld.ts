/**
 * Serializes structured data for embedding in a `<script type="application/ld+json">`.
 *
 * Escapes `<` to its `<` JSON unicode escape so that no user-controlled
 * string in the payload (a photo description, a username) can emit a literal
 * `</script>` and break out of the tag — the one load-bearing safety measure
 * for injecting JSON-LD via {@html}. JSON string semantics are preserved, so
 * consumers parse the identical object back.
 */
export function serializeJsonLd(data: unknown): string {
	return JSON.stringify(data).replace(/</g, '\\u003c');
}
