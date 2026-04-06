export interface LongPressOptions {
	duration?: number;
	onShortPress?: () => void;
	onLongPress?: () => void;
}

/**
 * Svelte action that adds long-press detection to an element.
 * Short press calls onShortPress, long press calls onLongPress.
 * The action suppresses the native click when a long press is detected.
 */
export function longPress(node: HTMLElement, options: LongPressOptions = {}) {
	let duration = options.duration ?? 500;
	let onShortPress = options.onShortPress;
	let onLongPress = options.onLongPress;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let wasLongPress = false;

	function handlePointerDown() {
		wasLongPress = false;
		timer = setTimeout(() => {
			wasLongPress = true;
			onLongPress?.();
		}, duration);
	}

	function handlePointerUp() {
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function handleClick(e: MouseEvent) {
		if (wasLongPress) {
			e.preventDefault();
			e.stopImmediatePropagation();
			wasLongPress = false;
			return;
		}
		onShortPress?.();
	}

	node.addEventListener('pointerdown', handlePointerDown);
	node.addEventListener('pointerup', handlePointerUp);
	node.addEventListener('pointercancel', handlePointerUp);
	node.addEventListener('click', handleClick);

	return {
		update(newOptions: LongPressOptions) {
			duration = newOptions.duration ?? 500;
			onShortPress = newOptions.onShortPress;
			onLongPress = newOptions.onLongPress;
		},
		destroy() {
			if (timer) clearTimeout(timer);
			node.removeEventListener('pointerdown', handlePointerDown);
			node.removeEventListener('pointerup', handlePointerUp);
			node.removeEventListener('pointercancel', handlePointerUp);
			node.removeEventListener('click', handleClick);
		}
	};
}
