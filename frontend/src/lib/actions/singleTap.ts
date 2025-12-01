export function singleTap(node: HTMLElement, callback: () => void) {

	function handleClick(event: MouseEvent) {
		callback();
		event.stopPropagation();
	}

	node.addEventListener('click', handleClick);

	return {
		destroy() {
			node.removeEventListener('click', handleClick);
		}
	};
}
