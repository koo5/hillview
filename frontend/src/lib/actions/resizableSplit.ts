/**
 * Draggable split pane action for Svelte
 * Allows users to resize two panels by dragging a divider between them
 */

export interface SplitOptions {
	direction?: 'horizontal' | 'vertical';
	minSize?: number; // Minimum size for each panel (in pixels)
	maxSize?: number; // Maximum size for first panel (in pixels)
	defaultSplit?: number; // Default split percentage (0-100)
	onResize?: (splitPercent: number) => void;
	disabled?: boolean;
	dividerSize?: number; // Divider thickness in pixels (default 12)
}

export function resizableSplit(node: HTMLElement, options: SplitOptions = {}) {
	const {
		direction = 'vertical',
		minSize = 100,
		maxSize,
		defaultSplit = 50,
		onResize,
		disabled = false,
		dividerSize = 12
	} = options;

	let isResizing = false;
	let startPos = 0;
	let startSplit = defaultSplit;
	let currentSplit = defaultSplit;

	// Create divider element
	const divider = document.createElement('div');
	divider.className = 'split-divider';
	const halfSize = Math.floor(dividerSize / 2);
	divider.style.cssText = `
		position: absolute;
		background: linear-gradient(135deg, #e2e8f0, #cbd5e1, #94a3b8);
		border: 1px solid rgba(148, 163, 184, 0.3);
		border-radius: 6px;
		cursor: ${options.direction === 'vertical' ? 'col-resize' : 'row-resize'};
		user-select: none;
		z-index: 1000;
		transition: all 0.2s ease;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
		${options.direction === 'vertical' ? `
			width: ${dividerSize}px;
			top: 0;
			bottom: 0;
			left: ${currentSplit}%;
			transform: translateX(-${halfSize}px);
		` : `
			height: ${dividerSize}px;
			left: 0;
			right: 0;
			top: ${currentSplit}%;
			transform: translateY(-${halfSize}px);
		`}
	`;

	// Add grip dots for visual feedback
	divider.innerHTML = `
		<div style="
			position: absolute;
			top: 50%;
			left: 50%;
			transform: translate(-50%, -50%);
			display: flex;
			${options.direction === 'vertical' ? 'flex-direction: column;' : 'flex-direction: row;'}
			gap: 2px;
		">
			<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
			<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
			<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
		</div>
	`;

	// Add hover effects
	divider.addEventListener('mouseenter', () => {
		if (!disabled) {
			divider.style.background = 'linear-gradient(135deg, #cbd5e1, #94a3b8, #64748b)';
			divider.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.15)';
		}
	});
	divider.addEventListener('mouseleave', () => {
		if (!isResizing) {
			divider.style.background = 'linear-gradient(135deg, #e2e8f0, #cbd5e1, #94a3b8)';
			divider.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';
		}
	});

	// Apply initial styles to container
	const updateContainerStyles = () => {
		node.style.position = 'relative';
		node.style.overflow = 'hidden';
	};

	// Update panel sizes based on split percentage
	const updatePanelSizes = () => {
		const panels = Array.from(node.children) as HTMLElement[];
		if (panels.length >= 2) {
			const firstPanel = panels[0];
			const secondPanel = panels.filter(p => p !== divider)[1];

			// Clear all positioning properties first
			firstPanel.style.cssText = '';
			secondPanel.style.cssText = '';

			// Apply common styles
			firstPanel.style.position = 'absolute';
			firstPanel.style.top = '0';
			firstPanel.style.left = '0';
			firstPanel.style.overflow = 'auto';
			secondPanel.style.position = 'absolute';
			secondPanel.style.overflow = 'auto';

			if (options.direction === 'vertical') {
				// Vertical split: side by side
				firstPanel.style.width = `${currentSplit}%`;
				firstPanel.style.height = '100%';
				secondPanel.style.width = `${100 - currentSplit}%`;
				secondPanel.style.height = '100%';
				secondPanel.style.right = '0';
				secondPanel.style.top = '0';
			} else {
				// Horizontal split: stacked
				firstPanel.style.height = `${currentSplit}%`;
				firstPanel.style.width = '100%';
				secondPanel.style.height = `${100 - currentSplit}%`;
				secondPanel.style.width = '100%';
				secondPanel.style.bottom = '0';
				secondPanel.style.left = '0';
			}
		}
	};

	// Update divider position
	const updateDividerPosition = () => {
		if (options.direction === 'vertical') {
			divider.style.left = `${currentSplit}%`;
		} else {
			divider.style.top = `${currentSplit}%`;
		}
	};

	// Calculate split percentage from mouse position
	const calculateSplitFromMouse = (clientX: number, clientY: number): number => {
		const rect = node.getBoundingClientRect();
		const pos = options.direction === 'vertical' ? clientX - rect.left : clientY - rect.top;
		const totalSize = options.direction === 'vertical' ? rect.width : rect.height;

		let splitPercent = (pos / totalSize) * 100;

		// Apply min/max constraints
		const minPercent = (minSize / totalSize) * 100;
		const maxPercent = maxSize ? Math.min((maxSize / totalSize) * 100, 100 - minPercent) : 100 - minPercent;

		splitPercent = Math.max(minPercent, Math.min(maxPercent, splitPercent));
		return splitPercent;
	};

	// Mouse event handlers
	const handleMouseDown = (e: MouseEvent) => {
		if (disabled) return;
		e.preventDefault();
		isResizing = true;
		startPos = options.direction === 'vertical' ? e.clientX : e.clientY;
		startSplit = currentSplit;
		divider.style.background = 'linear-gradient(135deg, #64748b, #475569, #334155)';
		divider.style.boxShadow = '0 6px 12px rgba(0, 0, 0, 0.2)';

		document.addEventListener('mousemove', handleMouseMove);
		document.addEventListener('mouseup', handleMouseUp);
		document.body.style.cursor = options.direction === 'vertical' ? 'col-resize' : 'row-resize';
		document.body.style.userSelect = 'none';
	};

	const handleMouseMove = (e: MouseEvent) => {
		if (!isResizing) return;

		currentSplit = calculateSplitFromMouse(e.clientX, e.clientY);

		// Update divider position immediately for smoother visual feedback
		requestAnimationFrame(() => {
			updateDividerPosition();
			updatePanelSizes();
		});

		if (onResize) {
			onResize(currentSplit);
		}
	};

	const handleMouseUp = () => {
		if (!isResizing) return;
		isResizing = false;
		divider.style.background = 'linear-gradient(135deg, #e2e8f0, #cbd5e1, #94a3b8)';
		divider.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';

		document.removeEventListener('mousemove', handleMouseMove);
		document.removeEventListener('mouseup', handleMouseUp);
		document.body.style.cursor = '';
		document.body.style.userSelect = '';
	};

	// Touch event handlers for mobile
	const handleTouchStart = (e: TouchEvent) => {
		if (disabled || e.touches.length !== 1) return;
		e.preventDefault();
		const touch = e.touches[0];
		handleMouseDown({
			preventDefault: () => {},
			clientX: touch.clientX,
			clientY: touch.clientY
		} as MouseEvent);
	};

	const handleTouchMove = (e: TouchEvent) => {
		if (!isResizing || e.touches.length !== 1) return;
		e.preventDefault();
		const touch = e.touches[0];
		handleMouseMove({
			clientX: touch.clientX,
			clientY: touch.clientY
		} as MouseEvent);
	};

	const handleTouchEnd = (e: TouchEvent) => {
		if (!isResizing) return;
		e.preventDefault();
		handleMouseUp();
	};

	// Initialize
	const init = () => {
		console.log('🔄SPLIT: resizableSplit.init called', JSON.stringify({
			direction,
			defaultSplit,
			currentSplit
		}));
		updateContainerStyles();
		node.appendChild(divider);
		updatePanelSizes();
		updateDividerPosition();

		// Add event listeners
		divider.addEventListener('mousedown', handleMouseDown);
		divider.addEventListener('touchstart', handleTouchStart);
		divider.addEventListener('touchmove', handleTouchMove);
		divider.addEventListener('touchend', handleTouchEnd);
	};

	// Public API for updating options
	const update = (newOptions: SplitOptions) => {
		console.log('🔄SPLIT: resizableSplit.update called', JSON.stringify({
			oldOptions: options,
			newOptions,
			oldDirection: direction,
			newDirection: newOptions.direction
		}));

		const oldDirection = options.direction;
		Object.assign(options, newOptions);

		// Update direction if it changed
		if (newOptions.direction && newOptions.direction !== oldDirection) {
			console.log('🔄SPLIT: Direction changed, updating divider and panels', JSON.stringify({
				from: oldDirection,
				to: newOptions.direction
			}));

			// Update divider styles for new direction
			const halfSize = Math.floor(options.dividerSize || 12) / 2;
			if (newOptions.direction === 'vertical') {
				divider.style.cssText = `
					position: absolute;
					background: linear-gradient(135deg, #e2e8f0, #cbd5e1, #94a3b8);
					border: 1px solid rgba(148, 163, 184, 0.3);
					border-radius: 6px;
					cursor: col-resize;
					user-select: none;
					z-index: 1000;
					transition: all 0.2s ease;
					box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
					width: ${options.dividerSize || 12}px;
					top: 0;
					bottom: 0;
					left: ${currentSplit}%;
					transform: translateX(-${halfSize}px);
				`;
				divider.innerHTML = `
					<div style="
						position: absolute;
						top: 50%;
						left: 50%;
						transform: translate(-50%, -50%);
						display: flex;
						flex-direction: column;
						gap: 2px;
					">
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
					</div>
				`;
			} else {
				divider.style.cssText = `
					position: absolute;
					background: linear-gradient(135deg, #e2e8f0, #cbd5e1, #94a3b8);
					border: 1px solid rgba(148, 163, 184, 0.3);
					border-radius: 6px;
					cursor: row-resize;
					user-select: none;
					z-index: 1000;
					transition: all 0.2s ease;
					box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
					height: ${options.dividerSize || 12}px;
					left: 0;
					right: 0;
					top: ${currentSplit}%;
					transform: translateY(-${halfSize}px);
				`;
				divider.innerHTML = `
					<div style="
						position: absolute;
						top: 50%;
						left: 50%;
						transform: translate(-50%, -50%);
						display: flex;
						flex-direction: row;
						gap: 2px;
					">
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
						<div style="width: 3px; height: 3px; background: rgba(71, 85, 105, 0.4); border-radius: 50%;"></div>
					</div>
				`;
			}

			updatePanelSizes();
		}

		if (newOptions.defaultSplit !== undefined) {
			currentSplit = newOptions.defaultSplit;
			updateDividerPosition();
			updatePanelSizes();
		}
		if (newOptions.disabled !== undefined) {
			divider.style.display = newOptions.disabled ? 'none' : 'block';
		}
	};

	// Cleanup
	const destroy = () => {
		if (divider.parentNode) {
			divider.parentNode.removeChild(divider);
		}
		document.removeEventListener('mousemove', handleMouseMove);
		document.removeEventListener('mouseup', handleMouseUp);
	};

	init();

	return {
		update,
		destroy
	};
}