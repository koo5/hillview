export function doubleTap(node: HTMLElement, callback: () => void) {
	let clickTimeout: ReturnType<typeof setTimeout> | undefined;

	function handleClick(event: MouseEvent) {
		if (clickTimeout) {
			// Second click - double tap
			clearTimeout(clickTimeout);
			clickTimeout = undefined;
			callback();
		} else {
			// First click - wait for potential second click
			clickTimeout = setTimeout(() => {
				clickTimeout = undefined;
				// Single click - dispatch original click event
				const clickEvent = new MouseEvent('click', {
					bubbles: event.bubbles,
					cancelable: event.cancelable,
					clientX: event.clientX,
					clientY: event.clientY,
					button: event.button,
					buttons: event.buttons
				});
				node.dispatchEvent(clickEvent);
			}, 300);
		}
		event.stopPropagation();
	}

	node.addEventListener('click', handleClick);

	return {
		destroy() {
			if (clickTimeout) {
				clearTimeout(clickTimeout);
			}
			node.removeEventListener('click', handleClick);
		}
	};
}