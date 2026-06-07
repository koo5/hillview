/**
 * Svelte action that focuses an element when it mounts.
 * Focus is deferred a frame so it survives portal moves
 * (re-parenting via appendChild blurs the focused element).
 */
export function autofocus(node: HTMLElement) {
	requestAnimationFrame(() => node.focus());
}
