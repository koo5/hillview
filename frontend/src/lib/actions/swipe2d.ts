interface Swipe2DOptions {
	onSwipe: (direction: 'left' | 'right' | 'up' | 'down') => void;
	onDrag?: (deltaX: number, deltaY: number) => void;
	onDragStart?: () => void;
	onDragEnd?: () => void;
	snapThreshold?: number;
	dampingFactor?: number;
	enableVisualFeedback?: boolean;
	dragStartThreshold?: number; // Minimum movement to start drag (prevents conflict with click)
	transformTarget?: HTMLElement; // Optional element to apply transforms to (instead of the node itself)
	// Boundary checking - which directions are allowed
	canGoLeft?: boolean;
	canGoRight?: boolean;
	canGoUp?: boolean;
	canGoDown?: boolean;
}

interface DragState {
	isDragging: boolean;
	hasMoved: boolean; // Track if we've moved enough to be considered a drag
	axisLocked: 'none' | 'horizontal' | 'vertical'; // Which axis movement is locked to
	startX: number;
	startY: number;
	currentX: number;
	currentY: number;
	initialTransformX: number;
	initialTransformY: number;
	pendingTransitionListener?: (e: TransitionEvent) => void; // Track active transition listener
}

export function swipe2d(node: HTMLElement, initialOptions: Swipe2DOptions) {
	// Store options in a mutable object
	let currentOptions = { ...initialOptions };

	// Helper function to destructure options with defaults
	function getOptionsWithDefaults(opts: Swipe2DOptions) {
		return {
			onSwipe: opts.onSwipe,
			onDrag: opts.onDrag,
			onDragStart: opts.onDragStart,
			onDragEnd: opts.onDragEnd,
			snapThreshold: opts.snapThreshold ?? 50,
			dampingFactor: opts.dampingFactor ?? 0.3,
			enableVisualFeedback: opts.enableVisualFeedback ?? true,
			dragStartThreshold: opts.dragStartThreshold ?? 10,
			transformTarget: opts.transformTarget,
			canGoLeft: opts.canGoLeft ?? true,
			canGoRight: opts.canGoRight ?? true,
			canGoUp: opts.canGoUp ?? true,
			canGoDown: opts.canGoDown ?? true
		};
	}

	// Get current options with defaults
	let optionsWithDefaults = getOptionsWithDefaults(currentOptions);
	let {
		onSwipe,
		onDrag,
		onDragStart,
		onDragEnd,
		snapThreshold,
		dampingFactor,
		enableVisualFeedback,
		dragStartThreshold,
		transformTarget,
		canGoLeft,
		canGoRight,
		canGoUp,
		canGoDown
	} = optionsWithDefaults;

	console.log('🢄swipe2d: Initialized with options:', optionsWithDefaults);

	let dragState: DragState = {
		isDragging: false,
		hasMoved: false,
		axisLocked: 'none',
		startX: 0,
		startY: 0,
		currentX: 0,
		currentY: 0,
		initialTransformX: 0,
		initialTransformY: 0,
		pendingTransitionListener: undefined
	};

	// Use transformTarget if provided, otherwise use the node itself
	let targetElement = transformTarget || node;

	// Store original transition for restoration
	let originalTransition = targetElement.style.transition;

	function getTransformValues(): { x: number; y: number } {
		const transform = window.getComputedStyle(targetElement).transform;
		if (transform === 'none') return { x: 0, y: 0 };

		const matrix = transform.match(/matrix.*\((.+)\)/)?.[1]?.split(', ');
		if (matrix && matrix.length >= 6) {
			return { x: parseFloat(matrix[4]), y: parseFloat(matrix[5]) };
		}
		return { x: 0, y: 0 };
	}

	function updateTransform(deltaX: number, deltaY: number) {
		if (!enableVisualFeedback) return;

		const x = dragState.initialTransformX + deltaX;
		const y = dragState.initialTransformY + deltaY;
		targetElement.style.transform = `translate3d(${x}px, ${y}px, 0)`;
	}

	function resetTransform() {
		if (!enableVisualFeedback) return;

		targetElement.style.transform = `translate3d(${dragState.initialTransformX}px, ${dragState.initialTransformY}px, 0)`;
	}

	function startDrag(x: number, y: number) {
		// If an animation is in progress, complete it immediately
		if (dragState.pendingTransitionListener) {
			// Manually trigger the completion logic without waiting for transition
			const listener = dragState.pendingTransitionListener;

			// Create a proper synthetic event that will pass the target check
			const syntheticEvent = {
				target: targetElement,
				propertyName: 'transform'
			} as TransitionEvent;

			// Call the handler directly
			listener(syntheticEvent);
		}

		dragState.startX = x;
		dragState.startY = y;
		dragState.currentX = x;
		dragState.currentY = y;
		dragState.isDragging = true;
		dragState.hasMoved = false;
		dragState.axisLocked = 'none';

		// Get initial transform values (should be 0,0 after reset)
		const initialTransform = getTransformValues();
		dragState.initialTransformX = initialTransform.x;
		dragState.initialTransformY = initialTransform.y;

		// Don't disable transitions yet - wait for movement
	}

	function updateDrag(x: number, y: number) {
		if (!dragState.isDragging) return false;

		dragState.currentX = x;
		dragState.currentY = y;

		const rawDeltaX = dragState.currentX - dragState.startX;
		const rawDeltaY = dragState.currentY - dragState.startY;

		// Check if we've moved enough to be considered a drag
		const totalMovement = Math.sqrt(rawDeltaX * rawDeltaX + rawDeltaY * rawDeltaY);

		if (!dragState.hasMoved && totalMovement >= dragStartThreshold) {
			// First time we've moved enough - determine axis and lock to it
			dragState.hasMoved = true;

			const absX = Math.abs(rawDeltaX);
			const absY = Math.abs(rawDeltaY);

			// Lock to the axis with more movement
			if (absX > absY) {
				dragState.axisLocked = 'horizontal';
			} else {
				dragState.axisLocked = 'vertical';
			}

			if (enableVisualFeedback) {
				targetElement.style.transition = 'none';
			}
			onDragStart?.();
		}

		// Only update visuals if we've moved enough
		if (dragState.hasMoved) {
			let dampedDeltaX = rawDeltaX * dampingFactor;
			let dampedDeltaY = rawDeltaY * dampingFactor;

			// Apply axis locking - zero out movement on the non-locked axis
			if (dragState.axisLocked === 'horizontal') {
				dampedDeltaY = 0;
				// Apply boundary checking for horizontal movement
				if ((dampedDeltaX > 0 && !canGoLeft) || (dampedDeltaX < 0 && !canGoRight)) {
					dampedDeltaX = 0;
				}
			} else if (dragState.axisLocked === 'vertical') {
				dampedDeltaX = 0;
				// Apply boundary checking for vertical movement
				if ((dampedDeltaY > 0 && !canGoUp) || (dampedDeltaY < 0 && !canGoDown)) {
					dampedDeltaY = 0;
				}
			}

			updateTransform(dampedDeltaX, dampedDeltaY);
			onDrag?.(dampedDeltaX, dampedDeltaY);
			return true; // Prevent default to stop other events
		}

		return false; // Don't prevent default - allow other handlers
	}

	function endDrag(x: number, y: number) {
		if (!dragState.isDragging) return;

		const finalDeltaX = x - dragState.startX;
		const finalDeltaY = y - dragState.startY;
		const wasDragging = dragState.hasMoved;

		dragState.isDragging = false;
		dragState.hasMoved = false;
		dragState.axisLocked = 'none';

		// Flag to prevent click events if we had a successful swipe
		let preventClick = false;

		// Only process swipe if we actually moved enough to be dragging
		if (wasDragging) {
			if (enableVisualFeedback) {
				// Re-enable transitions for snap animation
				targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
			}

			// Determine swipe direction with boundary checking
			const absX = Math.abs(finalDeltaX);
			const absY = Math.abs(finalDeltaY);
			let swipeSuccessful = false;


			if (absX > snapThreshold && absX > absY) {
				// Horizontal swipe - check boundaries
				const direction = finalDeltaX > 0 ? 'left' : 'right';
				const canMove = (direction === 'left' && canGoLeft) || (direction === 'right' && canGoRight);
				if (canMove) {
					// Call onSwipe immediately for responsive navigation
					//onSwipe(direction);

					// Re-enable transitions for slide animation
					if (enableVisualFeedback) {
						targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
					}

					// Complete the slide animation by moving one grid cell (1/3 of grid width = container width)
					const containerWidth = targetElement.offsetWidth / 3; // Grid is 300% wide, so 1/3 = container width
					const fullOffsetX = direction === 'left' ? containerWidth : -containerWidth;
					targetElement.style.transform = `translate3d(${dragState.initialTransformX + fullOffsetX}px, ${dragState.initialTransformY}px, 0)`;

					// Listen for transition end to reset transform
					const handleTransitionEnd = (e: TransitionEvent) => {
						if (e.target === targetElement && e.propertyName === 'transform') {
							onSwipe(direction);
							targetElement.removeEventListener('transitionend', handleTransitionEnd);
							dragState.pendingTransitionListener = undefined;
							// Disable transitions before reset to prevent unwanted animation
							targetElement.style.transition = 'none';
							resetTransform();
							// Re-enable transitions after reset
							setTimeout(() => {
								targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
							}, 0);
						}
					};
					dragState.pendingTransitionListener = handleTransitionEnd;
					targetElement.addEventListener('transitionend', handleTransitionEnd);
					swipeSuccessful = true;
					preventClick = true;
				}
			} else if (absY > snapThreshold && absY > absX) {
				// Vertical swipe - check boundaries
				const direction = finalDeltaY > 0 ? 'up' : 'down';
				const canMove = (direction === 'up' && canGoUp) || (direction === 'down' && canGoDown);
				if (canMove) {
					// Call onSwipe immediately for responsive navigation
					//onSwipe(direction);

					// Re-enable transitions for slide animation
					if (enableVisualFeedback) {
						targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
					}

					// Complete the slide animation by moving one grid cell (1/3 of grid height = container height)
					const containerHeight = targetElement.offsetHeight / 3; // Grid is 300% tall, so 1/3 = container height
					const fullOffsetY = direction === 'up' ? containerHeight : -containerHeight;
					targetElement.style.transform = `translate3d(${dragState.initialTransformX}px, ${dragState.initialTransformY + fullOffsetY}px, 0)`;

					// Listen for transition end to reset transform
					const handleTransitionEnd = (e: TransitionEvent) => {
						if (e.target === targetElement && e.propertyName === 'transform') {
							onSwipe(direction);
							targetElement.removeEventListener('transitionend', handleTransitionEnd);
							dragState.pendingTransitionListener = undefined;
							// Disable transitions before reset to prevent unwanted animation
							targetElement.style.transition = 'none';
							resetTransform();
							// Re-enable transitions after reset
							setTimeout(() => {
								targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
							}, 0);
						}
					};
					dragState.pendingTransitionListener = handleTransitionEnd;
					targetElement.addEventListener('transitionend', handleTransitionEnd);
					swipeSuccessful = true;
					preventClick = true;
				}
			}

			// Only reset transform immediately if swipe was not successful
			if (!swipeSuccessful) {
				resetTransform();
			}
			onDragEnd?.();
		}
		// If we weren't dragging, don't interfere - let other handlers work

		// Prevent click events for a short time after a successful swipe
		if (preventClick) {
			const preventClickHandler = (e: Event) => {
				e.preventDefault();
				e.stopPropagation();
			};

			// Add click prevention for a brief moment
			node.addEventListener('click', preventClickHandler, { capture: true });
			setTimeout(() => {
				node.removeEventListener('click', preventClickHandler, { capture: true });
			}, 50); // Brief delay to catch the click event
		}
	}

	function cancelDrag() {
		console.log('🢄swipe2d: cancelDrag called, isDragging:', dragState.isDragging);

		// Clean up any pending transition listener to prevent race conditions
		if (dragState.pendingTransitionListener) {
			targetElement.removeEventListener('transitionend', dragState.pendingTransitionListener);
			dragState.pendingTransitionListener = undefined;
		}

		// Always reset drag state and transform, regardless of current state
		dragState.isDragging = false;
		dragState.hasMoved = false;
		dragState.axisLocked = 'none';

		if (enableVisualFeedback) {
			// Force immediate reset without transition
			targetElement.style.transition = 'none';
			resetTransform();
			// Re-enable transitions for future interactions
			setTimeout(() => {
				targetElement.style.transition = originalTransition || 'transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)';
			}, 0);
		}

		onDragEnd?.();
	}

	// Touch event handlers
	function handleTouchStart(e: TouchEvent) {
		const touch = e.touches[0];
		startDrag(touch.clientX, touch.clientY);
	}

	function handleTouchMove(e: TouchEvent) {
		const touch = e.touches[0];
		if (updateDrag(touch.clientX, touch.clientY)) {
			e.preventDefault();
		}
	}

	function handleTouchEnd(e: TouchEvent) {
		const touch = e.changedTouches[0];
		endDrag(touch.clientX, touch.clientY);
	}

	function handleTouchCancel() {
		cancelDrag();
	}

	// Mouse event handlers
	function handleMouseDown(e: MouseEvent) {
		// Only handle left mouse button
		if (e.button !== 0) return;

		startDrag(e.clientX, e.clientY);
		e.preventDefault();
	}

	function handleMouseMove(e: MouseEvent) {
		if (updateDrag(e.clientX, e.clientY)) {
			e.preventDefault();
		}
	}

	function handleMouseUp(e: MouseEvent) {
		if (e.button !== 0) return;
		endDrag(e.clientX, e.clientY);
	}

	function handleMouseLeave() {
		// Cancel drag if mouse leaves the element
		cancelDrag();
	}

	// Add event listeners
	node.addEventListener('touchstart', handleTouchStart, { passive: false });
	node.addEventListener('touchmove', handleTouchMove, { passive: false });
	node.addEventListener('touchend', handleTouchEnd);
	node.addEventListener('touchcancel', handleTouchCancel);

	node.addEventListener('mousedown', handleMouseDown);
	node.addEventListener('mousemove', handleMouseMove);
	node.addEventListener('mouseup', handleMouseUp);
	node.addEventListener('mouseleave', handleMouseLeave);

	// Prevent context menu on right click during drag
	node.addEventListener('contextmenu', (e) => {
		if (dragState.isDragging) {
			e.preventDefault();
		}
	});

	const actionInstance = {
		destroy() {
			node.removeEventListener('touchstart', handleTouchStart);
			node.removeEventListener('touchmove', handleTouchMove);
			node.removeEventListener('touchend', handleTouchEnd);
			node.removeEventListener('touchcancel', handleTouchCancel);

			node.removeEventListener('mousedown', handleMouseDown);
			node.removeEventListener('mousemove', handleMouseMove);
			node.removeEventListener('mouseup', handleMouseUp);
			node.removeEventListener('mouseleave', handleMouseLeave);

			// Restore original styles
			targetElement.style.transition = originalTransition;

			// Remove reference from node
			delete (node as any).__swipe2d_action;
		},

		update(newOptions: Swipe2DOptions) {
			console.log('🢄swipe2d: update called with newOptions:', newOptions);
			// Only update boundary parameters and transform target
			if (newOptions.canGoLeft !== undefined) canGoLeft = newOptions.canGoLeft;
			if (newOptions.canGoRight !== undefined) canGoRight = newOptions.canGoRight;
			if (newOptions.canGoUp !== undefined) canGoUp = newOptions.canGoUp;
			if (newOptions.canGoDown !== undefined) canGoDown = newOptions.canGoDown;

			// Update transform target if provided
			if (newOptions.transformTarget !== undefined) {
				const oldTargetElement = targetElement;
				transformTarget = newOptions.transformTarget;
				targetElement = transformTarget || node;

				// Only update originalTransition if target element actually changed
				if (targetElement !== oldTargetElement) {
					originalTransition = targetElement.style.transition;
				}
			}
		},

		reset() {
			// Public method to reset drag state (useful when other interactions interfere)
			cancelDrag();
		}
	};

	// Store action instance on the node for external access
	(node as any).__swipe2d_action = actionInstance;

	return actionInstance;
}
