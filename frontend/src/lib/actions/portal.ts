/**
 * Svelte action that moves an element to document.body
 * This is useful for modals/dialogs that need to escape
 * transformed ancestors which break position:fixed
 */
export function portal(node: HTMLElement) {
	// Move to body
	document.body.appendChild(node);

	return {
		destroy() {
			// Clean up when component is destroyed
			if (node.parentNode) {
				node.parentNode.removeChild(node);
			}
		}
	};
}
