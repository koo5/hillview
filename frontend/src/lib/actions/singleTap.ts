export interface SingleTapOptions {
	callback: () => void;
	/** Ignore taps within this many pixels of the viewport edge (default 0) */
	edgeMargin?: number;
}

export function singleTap(node: HTMLElement, opts: (() => void) | SingleTapOptions) {
	let callback: () => void;
	let edgeMargin: number;

	function applyOpts(o: (() => void) | SingleTapOptions) {
		if (typeof o === 'function') {
			callback = o;
			edgeMargin = 0;
		} else {
			callback = o.callback;
			edgeMargin = o.edgeMargin ?? 0;
		}
	}

	applyOpts(opts);

	function handleClick(event: MouseEvent) {
		if (edgeMargin > 0) {
			const x = event.clientX;
			const y = event.clientY;
			if (
				x < edgeMargin ||
				y < edgeMargin ||
				x > window.innerWidth - edgeMargin ||
				y > window.innerHeight - edgeMargin
			) {
				return;
			}
		}
		callback();
		event.stopPropagation();
	}

	node.addEventListener('click', handleClick);

	return {
		update(newOpts: (() => void) | SingleTapOptions) {
			applyOpts(newOpts);
		},
		destroy() {
			node.removeEventListener('click', handleClick);
		}
	};
}
