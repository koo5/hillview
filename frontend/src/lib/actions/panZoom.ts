interface PanZoomState {
	scale: number;
	translateX: number;
	translateY: number;
}

interface PanZoomOptions {
	onUpdate: (state: PanZoomState) => void;
	initialScale?: number;
	minScale?: number;
	maxScale?: number;
	imageWidth?: number;
	imageHeight?: number;
	containerWidth?: number;
	containerHeight?: number;
}

export function panZoom(node: HTMLElement, options: PanZoomOptions) {
	let scale = options.initialScale || 1;
	let translateX = 0;
	let translateY = 0;

	const minScale = options.minScale || 0.5;
	const maxScale = options.maxScale || 5;


	// Touch handling
	let initialDistance = 0;
	let initialScale = 1;
	let initialX = 0;
	let initialY = 0;
	let lastTouchX = 0;
	let lastTouchY = 0;
	let isPinching = false;
	let isPanning = false;

	// Mouse handling
	let isDragging = false;
	let lastMouseX = 0;
	let lastMouseY = 0;

	function constrainPan() {
		if (!options.imageWidth || !options.imageHeight || !options.containerWidth || !options.containerHeight) {
			return; // Can't constrain without dimensions
		}

		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;

		const beforeX = translateX;
		const beforeY = translateY;

		// Constraint logic: center all images, allow panning within reasonable bounds
		if (scaledImageWidth <= options.containerWidth) {
			// Image is smaller than container, keep it centered
			translateX = (options.containerWidth - scaledImageWidth) / 2;
		} else {
			// Image is larger than container, allow panning around center
			// Center position would be: (containerWidth - scaledImageWidth) / 2 (negative value)
			const centerX = (options.containerWidth - scaledImageWidth) / 2;
			const excess = scaledImageWidth - options.containerWidth;
			const minTranslateX = centerX - excess / 2; // Can pan left from center
			const maxTranslateX = centerX + excess / 2; // Can pan right from center
			translateX = Math.max(minTranslateX, Math.min(maxTranslateX, translateX));
		}

		if (scaledImageHeight <= options.containerHeight) {
			// Image is smaller than container, keep it centered
			translateY = (options.containerHeight - scaledImageHeight) / 2;
		} else {
			// Image is larger than container, allow panning around center
			// Center position would be: (containerHeight - scaledImageHeight) / 2 (negative value)
			const centerY = (options.containerHeight - scaledImageHeight) / 2;
			const excess = scaledImageHeight - options.containerHeight;
			const minTranslateY = centerY - excess / 2; // Can pan up from center
			const maxTranslateY = centerY + excess / 2; // Can pan down from center
			translateY = Math.max(minTranslateY, Math.min(maxTranslateY, translateY));
		}
	}

	// Convert screen coordinates to image-space coordinates
	function screenToImageSpace(screenX: number, screenY: number) {
		if (!options.imageWidth || !options.imageHeight) {
			return { x: 0, y: 0 };
		}

		// translateX/Y are now screen coordinates, so this is simple
		const imageRelativeX = screenX - translateX;
		const imageRelativeY = screenY - translateY;

		// Convert from CSS pixels to actual image pixels
		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;
		const imagePixelX = imageRelativeX * (options.imageWidth / scaledImageWidth);
		const imagePixelY = imageRelativeY * (options.imageHeight / scaledImageHeight);


		// Return actual image coordinates (0,0 at top-left of image)
		return {
			x: imagePixelX,
			y: imagePixelY
		};
	}

	// Convert image-space point to container-relative coordinates
	function imageToContainerSpace(imageX: number, imageY: number) {
		return {
			x: translateX + imageX * scale,
			y: translateY + imageY * scale
		};
	}

	// Apply zoom-to-point transformation
	function applyZoomToPoint(containerX: number, containerY: number, screenX: number, screenY: number, newScale: number) {
		// Find the point in the image that's currently under the screen position
		const imagePoint = screenToImageSpace(screenX, screenY);


		// Calculate new scaled dimensions
		const newScaledImageWidth = (options.imageWidth || 0) * newScale;
		const newScaledImageHeight = (options.imageHeight || 0) * newScale;

		// Position image so the same image point stays under the screen position
		const newTranslateX = screenX - (imagePoint.x / (options.imageWidth || 1)) * newScaledImageWidth;
		const newTranslateY = screenY - (imagePoint.y / (options.imageHeight || 1)) * newScaledImageHeight;

		// Update state
		translateX = newTranslateX;
		translateY = newTranslateY;
		scale = newScale;
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
		if (event.touches.length === 2) {
			isPinching = true;
			isPanning = false;
			initialDistance = getDistance(event.touches);
			initialScale = scale;
		} else if (event.touches.length === 1) {
			// Allow panning if image is larger than container in any dimension
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
			}
		}
	}

	function handleTouchMove(event: TouchEvent) {
		event.preventDefault();

		if (isPinching && event.touches.length === 2) {
			const currentDistance = getDistance(event.touches);
			const scaleChange = currentDistance / initialDistance;
			const newScale = Math.max(minScale, Math.min(maxScale, initialScale * scaleChange));

			// Calculate the center point of the pinch gesture
			const centerX = (event.touches[0].clientX + event.touches[1].clientX) / 2;
			const centerY = (event.touches[0].clientY + event.touches[1].clientY) / 2;

			// Get container bounds to convert to relative coordinates
			const rect = (event.target as HTMLElement).getBoundingClientRect();
			const relativeX = centerX - rect.left;
			const relativeY = centerY - rect.top;

			// Apply zoom-to-point for pinch center
			const containerX = relativeX - (options.containerWidth || 0) / 2;
			const containerY = relativeY - (options.containerHeight || 0) / 2;

			applyZoomToPoint(containerX, containerY, centerX, centerY, newScale);

			updateState();
		} else if (isPanning && event.touches.length === 1) {
			const deltaX = event.touches[0].clientX - lastTouchX;
			const deltaY = event.touches[0].clientY - lastTouchY;
			// Work in actual pixels now
			translateX = initialX + deltaX;
			translateY = initialY + deltaY;
			updateState();
		}
	}

	function handleTouchEnd() {
		isPinching = false;
		isPanning = false;
	}

	// Mouse events
	function handleMouseDown(event: MouseEvent) {
		console.log('🖱️ [PanZoom] Mouse down');
		// Check if we have valid dimensions
		if (!options.imageWidth || !options.imageHeight || !options.containerWidth || !options.containerHeight) {
			console.log('🖱️ [PanZoom] Missing dimensions, allowing pan anyway');
			isDragging = true;
			initialX = translateX;
			initialY = translateY;
			lastMouseX = event.clientX;
			lastMouseY = event.clientY;
			event.preventDefault();
			return;
		}

		// Allow panning if image is larger than container in any dimension
		const scaledImageWidth = options.imageWidth * scale;
		const scaledImageHeight = options.imageHeight * scale;
		const canPan = scaledImageWidth > options.containerWidth ||
					   scaledImageHeight > options.containerHeight;

		console.log('🖱️ [PanZoom] Can pan?', canPan, 'scaledSize:', scaledImageWidth, 'x', scaledImageHeight, 'container:', options.containerWidth, 'x', options.containerHeight);

		if (canPan) {
			isDragging = true;
			initialX = translateX;
			initialY = translateY;
			lastMouseX = event.clientX;
			lastMouseY = event.clientY;
			event.preventDefault();
			console.log('🖱️ [PanZoom] Started dragging');
		}
	}

	function handleMouseMove(event: MouseEvent) {
		if (isDragging) {
			const deltaX = event.clientX - lastMouseX;
			const deltaY = event.clientY - lastMouseY;
			// Work in actual pixels now
			translateX = initialX + deltaX;
			translateY = initialY + deltaY;
			updateState();
		}
	}

	function handleMouseUp() {
		isDragging = false;
	}


	// Wheel events
	function handleWheel(event: WheelEvent) {
		event.preventDefault();
		const scaleChange = event.deltaY > 0 ? 0.9 : 1.1;
		const newScale = Math.max(minScale, Math.min(maxScale, scale * scaleChange));

		// Calculate zoom-to-point for mouse position
		const rect = (event.target as HTMLElement).getBoundingClientRect();
		const relativeX = event.clientX - rect.left;
		const relativeY = event.clientY - rect.top;

		console.log('🎡 [PanZoom] Wheel zoom debug:', {
			mousePos: { x: event.clientX, y: event.clientY },
			rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
			relativePos: { x: relativeX, y: relativeY },
			containerSize: { w: options.containerWidth, h: options.containerHeight },
			scaleChange: { from: scale, to: newScale },
			currentTranslate: { x: translateX, y: translateY }
		});

		// Store old values for comparison
		const oldTranslateX = translateX;
		const oldTranslateY = translateY;

		// Apply zoom-to-point for mouse position
		const containerX = relativeX - (options.containerWidth || 0) / 2;
		const containerY = relativeY - (options.containerHeight || 0) / 2;

		applyZoomToPoint(containerX, containerY, event.clientX, event.clientY, newScale);

		updateState();
	}

	// Double click to zoom
	let lastClickTime = 0;
	function handleClick(event: MouseEvent) {
		const now = Date.now();
		if (now - lastClickTime < 300) {
			// Double click - toggle between initial scale and 2x initial scale
			const initialScale = options.initialScale || 1;
			if (Math.abs(scale - initialScale) < 0.01) { // Close to initial scale
				scale = initialScale * 2;
			} else {
				scale = initialScale;
				// Center the image when resetting (always)
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

	// Apply initial constraints to center the image
	console.log('📐 [PanZoom] Initial setup with dimensions:', {
		imageWidth: options.imageWidth,
		imageHeight: options.imageHeight,
		containerWidth: options.containerWidth,
		containerHeight: options.containerHeight
	});
	updateState();

	return {
		update(newOptions: PanZoomOptions) {
			console.log('📐 [PanZoom] Action updated with options:', newOptions);
			options = newOptions;
			// Re-apply constraints when options change (e.g., when dimensions become available)
			updateState();
		},
		destroy() {
			node.removeEventListener('touchstart', handleTouchStart);
			node.removeEventListener('touchmove', handleTouchMove);
			node.removeEventListener('touchend', handleTouchEnd);
			node.removeEventListener('mousedown', handleMouseDown);
			node.removeEventListener('wheel', handleWheel);
			node.removeEventListener('click', handleClick);
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		}
	};
}
