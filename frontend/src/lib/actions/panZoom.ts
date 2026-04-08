interface PanZoomState {
	scale: number;
	translateX: number;
	translateY: number;
}

interface PanZoomOptions {
	onUpdate: (state: PanZoomState) => void;
	onZoomChange?: (isZoomed: boolean) => void;
	/** Fires when a touch pinch gesture ends with the user still zoomed in
	 *  (scale > 1.01) in embedded mode. Used by the Gallery to promote the
	 *  inline preview into the full ZoomView after the user releases. */
	onPinchEnd?: () => void;
	initialScale?: number;
	minScale?: number;
	maxScale?: number;
	imageWidth?: number;
	imageHeight?: number;
	containerWidth?: number;
	containerHeight?: number;
	/** When true, only capture events when pinching or zoomed in.
	 *  Single-touch at 1x scale passes through to parent handlers (e.g. swipe2d). */
	isEmbedded?: boolean;
}

export function panZoom(node: HTMLElement, options: PanZoomOptions) {
	let scale = options.initialScale || 1;
	let translateX = 0;
	let translateY = 0;

	let minScale = options.minScale || 0.5;
	let maxScale = options.maxScale || 5;
	let isEmbedded = options.isEmbedded || false;

	// Track whether we're in zoomed state (for embedded mode)
	let wasZoomed = false;

	function isZoomed() {
		return scale > 1.01;
	}

	function checkZoomChange() {
		const zoomed = isZoomed();
		if (zoomed !== wasZoomed) {
			wasZoomed = zoomed;
			options.onZoomChange?.(zoomed);
		}
	}

	// Touch handling
	let initialDistance = 0;
	let pinchInitialScale = 1;
	let initialX = 0;
	let initialY = 0;
	let lastTouchX = 0;
	let lastTouchY = 0;
	let isPinching = false;
	let isPanning = false;
	// True from 2-finger touchstart until all fingers are fully released,
	// so we can defer onPinchEnd until event.touches.length === 0 (covers
	// multi-step releases where one finger lifts before the other).
	let pinchGestureInProgress = false;

	// Mouse handling
	let isDragging = false;
	let lastMouseX = 0;
	let lastMouseY = 0;

	function constrainPan() {
		if (!options.containerWidth || !options.containerHeight) {
			return;
		}

		if (isEmbedded) {
			// Embedded mode: transform is translate(tx,ty) scale(s) with origin 0 0.
			// Scaled content spans (tx, ty) to (tx + cw*s, ty + ch*s).
			// Clamp so viewport stays within scaled content.
			const cw = options.containerWidth;
			const ch = options.containerHeight;
			translateX = Math.max(cw * (1 - scale), Math.min(0, translateX));
			translateY = Math.max(ch * (1 - scale), Math.min(0, translateY));
			return;
		}

		if (!options.imageWidth || !options.imageHeight) return;

		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;

		if (scaledImageWidth <= options.containerWidth) {
			translateX = (options.containerWidth - scaledImageWidth) / 2;
		} else {
			const centerX = (options.containerWidth - scaledImageWidth) / 2;
			const excess = scaledImageWidth - options.containerWidth;
			const minTranslateX = centerX - excess / 2;
			const maxTranslateX = centerX + excess / 2;
			translateX = Math.max(minTranslateX, Math.min(maxTranslateX, translateX));
		}

		if (scaledImageHeight <= options.containerHeight) {
			translateY = (options.containerHeight - scaledImageHeight) / 2;
		} else {
			const centerY = (options.containerHeight - scaledImageHeight) / 2;
			const excess = scaledImageHeight - options.containerHeight;
			const minTranslateY = centerY - excess / 2;
			const maxTranslateY = centerY + excess / 2;
			translateY = Math.max(minTranslateY, Math.min(maxTranslateY, translateY));
		}
	}

	function screenToImageSpace(screenX: number, screenY: number) {
		if (!options.imageWidth || !options.imageHeight) {
			return { x: 0, y: 0 };
		}
		const imageRelativeX = screenX - translateX;
		const imageRelativeY = screenY - translateY;
		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;
		const imagePixelX = imageRelativeX * (options.imageWidth / scaledImageWidth);
		const imagePixelY = imageRelativeY * (options.imageHeight / scaledImageHeight);
		return { x: imagePixelX, y: imagePixelY };
	}

	function applyZoomToPoint(containerX: number, containerY: number, screenX: number, screenY: number, newScale: number) {
		const imagePoint = screenToImageSpace(screenX, screenY);
		const newScaledImageWidth = (options.imageWidth || 0) * newScale;
		const newScaledImageHeight = (options.imageHeight || 0) * newScale;
		const newTranslateX = screenX - (imagePoint.x / (options.imageWidth || 1)) * newScaledImageWidth;
		const newTranslateY = screenY - (imagePoint.y / (options.imageHeight || 1)) * newScaledImageHeight;
		translateX = newTranslateX;
		translateY = newTranslateY;
		scale = newScale;
	}

	function resetToIdentity() {
		scale = 1;
		translateX = 0;
		translateY = 0;
		updateState();
		checkZoomChange();
	}

	function updateState() {
		constrainPan();
		options.onUpdate({ scale, translateX, translateY });
	}

	function getDistance(touches: TouchList): number {
		const dx = touches[0].clientX - touches[1].clientX;
		const dy = touches[0].clientY - touches[1].clientY;
		return Math.sqrt(dx * dx + dy * dy);
	}

	// Touch events
	function handleTouchStart(event: TouchEvent) {
		console.log('🢄panZoom.touchstart ' + JSON.stringify({touches: event.touches.length, isEmbedded, scale}));
		if (event.touches.length === 2) {
			isPinching = true;
			pinchGestureInProgress = true;
			isPanning = false;
			initialDistance = getDistance(event.touches);
			pinchInitialScale = scale;
			// In embedded mode, stop propagation so swipe2d doesn't see the pinch
			if (isEmbedded) {
				event.stopPropagation();
			}
		} else if (event.touches.length === 1) {
			// In embedded mode at 1x: don't capture, let swipe2d handle it
			if (isEmbedded && !isZoomed()) {
				return;
			}
			const scaledImageWidth = (options.imageWidth || 0) * scale;
			const scaledImageHeight = (options.imageHeight || 0) * scale;
			const canPan = scaledImageWidth > (options.containerWidth || 0) ||
						   scaledImageHeight > (options.containerHeight || 0);
			if (canPan) {
				isPanning = true;
				isPinching = false;
				initialX = translateX;
				initialY = translateY;
				lastTouchX = event.touches[0].clientX;
				lastTouchY = event.touches[0].clientY;
				if (isEmbedded) {
					event.stopPropagation();
				}
			}
		}
	}

	function handleTouchMove(event: TouchEvent) {
		if (isPinching && event.touches.length === 2) {
			event.preventDefault();
			if (isEmbedded) event.stopPropagation();

			const currentDistance = getDistance(event.touches);
			const scaleChange = currentDistance / initialDistance;
			const newScale = Math.max(minScale, Math.min(maxScale, pinchInitialScale * scaleChange));

			const centerX = (event.touches[0].clientX + event.touches[1].clientX) / 2;
			const centerY = (event.touches[0].clientY + event.touches[1].clientY) / 2;

			const rect = node.getBoundingClientRect();
			const relativeX = centerX - rect.left;
			const relativeY = centerY - rect.top;

			const containerX = relativeX - (options.containerWidth || 0) / 2;
			const containerY = relativeY - (options.containerHeight || 0) / 2;

			applyZoomToPoint(containerX, containerY, centerX, centerY, newScale);
			updateState();
			checkZoomChange();
		} else if (isPanning && event.touches.length === 1) {
			event.preventDefault();
			if (isEmbedded) event.stopPropagation();

			const deltaX = event.touches[0].clientX - lastTouchX;
			const deltaY = event.touches[0].clientY - lastTouchY;
			translateX = initialX + deltaX;
			translateY = initialY + deltaY;
			updateState();
		} else if (isEmbedded && !isPinching && !isPanning) {
			// Not our gesture, let it through
			return;
		} else {
			// Original behavior for non-embedded
			if (!isEmbedded) event.preventDefault();
		}
	}

	function handleTouchEnd(event: TouchEvent) {
		const wasPinching = isPinching;
		isPinching = false;
		isPanning = false;

		console.log('🢄panZoom.touchend ' + JSON.stringify({
			touchesLeft: event.touches.length,
			wasPinching,
			pinchGestureInProgress,
			scale,
			isEmbedded,
			hasOnPinchEnd: !!options.onPinchEnd,
		}));

		// In embedded mode, snap back to 1x if pinch ended below threshold.
		// (Preserves the existing first-touchend reset behavior.)
		if (isEmbedded && wasPinching && scale <= 1.01) {
			resetToIdentity();
			pinchGestureInProgress = false;
		} else if (event.touches.length === 0) {
			// All fingers off: if this concluded a pinch gesture that left us
			// zoomed in, notify so the host can promote to a full viewer.
			if (isEmbedded && pinchGestureInProgress && scale > 1.01) {
				console.log('🢄panZoom.touchend: firing onPinchEnd ' + JSON.stringify({scale}));
				options.onPinchEnd?.();
			}
			pinchGestureInProgress = false;
		}
		checkZoomChange();
	}

	// Mouse events
	function handleMouseDown(event: MouseEvent) {
		if (event.button !== 0) return;

		// In embedded mode at 1x: don't capture mouse, let swipe2d handle it
		if (isEmbedded && !isZoomed()) return;

		if (!options.imageWidth || !options.imageHeight || !options.containerWidth || !options.containerHeight) {
			isDragging = true;
			initialX = translateX;
			initialY = translateY;
			lastMouseX = event.clientX;
			lastMouseY = event.clientY;
			event.preventDefault();
			return;
		}

		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;
		const canPan = scaledImageWidth > options.containerWidth ||
					   scaledImageHeight > options.containerHeight;

		if (canPan) {
			isDragging = true;
			initialX = translateX;
			initialY = translateY;
			lastMouseX = event.clientX;
			lastMouseY = event.clientY;
			event.preventDefault();
		}
	}

	let hasDragged = false;

	function handleMouseMove(event: MouseEvent) {
		if (isDragging) {
			const deltaX = event.clientX - lastMouseX;
			const deltaY = event.clientY - lastMouseY;
			if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) {
				hasDragged = true;
			}
			translateX = initialX + deltaX;
			translateY = initialY + deltaY;
			updateState();
		}
	}

	function handleMouseUp() {
		if (isDragging && hasDragged) {
			// Suppress the click that follows a drag-to-pan
			const suppress = (e: Event) => { e.preventDefault(); e.stopPropagation(); };
			node.addEventListener('click', suppress, { capture: true, once: true });
			setTimeout(() => node.removeEventListener('click', suppress, { capture: true }), 50);
		}
		isDragging = false;
		hasDragged = false;
	}

	// Wheel events
	function handleWheel(event: WheelEvent) {
		event.preventDefault();
		const scaleChange = event.deltaY > 0 ? 0.9 : 1.1;
		const newScale = Math.max(minScale, Math.min(maxScale, scale * scaleChange));

		const rect = node.getBoundingClientRect();
		const relativeX = event.clientX - rect.left;
		const relativeY = event.clientY - rect.top;

		const containerX = relativeX - (options.containerWidth || 0) / 2;
		const containerY = relativeY - (options.containerHeight || 0) / 2;

		applyZoomToPoint(containerX, containerY, event.clientX, event.clientY, newScale);
		updateState();
		checkZoomChange();

		// In embedded mode, snap back if scrolled below 1x
		if (isEmbedded && scale <= 1.01) {
			resetToIdentity();
		}
	}

	// Double click to zoom (disabled in embedded mode — conflicts with singleTap)
	let lastClickTime = 0;
	function handleClick(event: MouseEvent) {
		if (isEmbedded) return;

		const target = event.target as HTMLElement;
		if (target.closest('.filename-overlay')) return;

		const now = Date.now();
		if (now - lastClickTime < 300) {
			const initScale = options.initialScale || 1;
			if (Math.abs(scale - initScale) < 0.01) {
				scale = initScale * 2;
			} else {
				scale = initScale;
				if (options.imageWidth && options.imageHeight && options.containerWidth && options.containerHeight) {
					const scaledWidth = options.imageWidth * scale;
					const scaledHeight = options.imageHeight * scale;
					translateX = (options.containerWidth - scaledWidth) / 2;
					translateY = (options.containerHeight - scaledHeight) / 2;
				} else {
					translateX = 0;
					translateY = 0;
				}
			}
			updateState();
			checkZoomChange();
		}
		lastClickTime = now;
	}

	// Add event listeners
	node.addEventListener('touchstart', handleTouchStart, { passive: false });
	node.addEventListener('touchmove', handleTouchMove, { passive: false });
	node.addEventListener('touchend', handleTouchEnd);
	node.addEventListener('mousedown', handleMouseDown);
	node.addEventListener('wheel', handleWheel, { passive: false });
	node.addEventListener('click', handleClick);

	// Global mouse events for dragging
	document.addEventListener('mousemove', handleMouseMove);
	document.addEventListener('mouseup', handleMouseUp);

	if (!isEmbedded) {
		updateState();
	}

	const actionInstance = {
		update(newOptions: PanZoomOptions) {
			options = newOptions;
			minScale = newOptions.minScale || 0.5;
			maxScale = newOptions.maxScale || 5;
			isEmbedded = newOptions.isEmbedded || false;
			if (!isEmbedded) {
				updateState();
			}
		},
		/** Reset zoom to 1x and clear pan */
		reset: resetToIdentity,
		destroy() {
			node.removeEventListener('touchstart', handleTouchStart);
			node.removeEventListener('touchmove', handleTouchMove);
			node.removeEventListener('touchend', handleTouchEnd);
			node.removeEventListener('mousedown', handleMouseDown);
			node.removeEventListener('wheel', handleWheel);
			node.removeEventListener('click', handleClick);
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
			delete (node as any).__panZoom_action;
		}
	};

	(node as any).__panZoom_action = actionInstance;
	return actionInstance;
}
