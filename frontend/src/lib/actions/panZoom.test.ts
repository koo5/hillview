import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { panZoom } from './panZoom';

describe('panZoom action', () => {
	let node: HTMLDivElement;
	let lastState: { scale: number; translateX: number; translateY: number };
	let zoomChanges: boolean[];

	function createAction(overrides = {}) {
		const defaults = {
			onUpdate: (state: any) => { lastState = state; },
			onZoomChange: (isZoomed: boolean) => { zoomChanges.push(isZoomed); },
			initialScale: 1,
			minScale: 0.5,
			maxScale: 5,
			imageWidth: 800,
			imageHeight: 600,
			containerWidth: 400,
			containerHeight: 300,
		};
		return panZoom(node, { ...defaults, ...overrides });
	}

	beforeEach(() => {
		node = document.createElement('div');
		// getBoundingClientRect is needed by wheel handler
		node.getBoundingClientRect = () => ({
			x: 0, y: 0, width: 400, height: 300,
			top: 0, left: 0, right: 400, bottom: 300,
			toJSON: () => {},
		});
		document.body.appendChild(node);
		lastState = { scale: 1, translateX: 0, translateY: 0 };
		zoomChanges = [];
	});

	afterEach(() => {
		document.body.removeChild(node);
	});

	describe('initialization', () => {
		it('calls onUpdate on init with scale 1', () => {
			const action = createAction();
			expect(lastState.scale).toBe(1);
			action.destroy();
		});

		it('does not call onUpdate on init in embedded mode', () => {
			const spy = vi.fn();
			const action = createAction({ isEmbedded: true, onUpdate: spy });
			expect(spy).not.toHaveBeenCalled();
			action.destroy();
		});
	});

	describe('wheel zoom', () => {
		it('zooms in on wheel up', () => {
			const action = createAction();
			const initialScale = lastState.scale;
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
			}));
			expect(lastState.scale).toBeGreaterThan(initialScale);
			action.destroy();
		});

		it('zooms out on wheel down', () => {
			const action = createAction();
			// First zoom in so we can zoom out
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
			}));
			const zoomedScale = lastState.scale;
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: 100, clientX: 200, clientY: 150, bubbles: true,
			}));
			expect(lastState.scale).toBeLessThan(zoomedScale);
			action.destroy();
		});

		it('respects maxScale', () => {
			const action = createAction({ maxScale: 2 });
			// Many zoom-in events
			for (let i = 0; i < 50; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			expect(lastState.scale).toBeLessThanOrEqual(2);
			action.destroy();
		});

		it('respects minScale', () => {
			const action = createAction({ minScale: 0.5 });
			for (let i = 0; i < 50; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: 100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			expect(lastState.scale).toBeGreaterThanOrEqual(0.5);
			action.destroy();
		});
	});

	describe('zoom change callback', () => {
		it('fires onZoomChange(true) when zooming past 1.01', () => {
			const action = createAction();
			// Zoom in
			for (let i = 0; i < 5; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			expect(zoomChanges).toContain(true);
			action.destroy();
		});

		it('fires onZoomChange(false) when zooming back to ~1', () => {
			const action = createAction();
			// Zoom in
			for (let i = 0; i < 3; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			// Zoom back out
			for (let i = 0; i < 30; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: 100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			expect(zoomChanges).toContain(false);
			action.destroy();
		});
	});

	describe('reset', () => {
		it('resets to scale 1 and translate 0,0', () => {
			const action = createAction();
			// Zoom in
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
			}));
			expect(lastState.scale).not.toBe(1);
			action.reset();
			expect(lastState.scale).toBe(1);
			expect(lastState.translateX).toBe(0);
			expect(lastState.translateY).toBe(0);
			action.destroy();
		});
	});

	describe('embedded mode', () => {
		it('snaps back to 1x on wheel when scale drops below 1.01', () => {
			const action = createAction({ isEmbedded: true });
			// Zoom out — should snap back to 1
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: 100, clientX: 200, clientY: 150, bubbles: true,
			}));
			expect(lastState.scale).toBe(1);
			expect(lastState.translateX).toBe(0);
			expect(lastState.translateY).toBe(0);
			action.destroy();
		});
	});

	describe('constrainPan', () => {
		it('centers small images in container (non-embedded)', () => {
			// Image is smaller than container when at 1x
			const action = createAction({
				imageWidth: 200,
				imageHeight: 150,
				containerWidth: 400,
				containerHeight: 300,
			});
			// At scale 1, image (200x150) is smaller than container (400x300)
			// constrainPan should center: tx = (400-200)/2 = 100
			expect(lastState.translateX).toBeCloseTo(100);
			expect(lastState.translateY).toBeCloseTo(75);
			action.destroy();
		});

		it('allows panning when image is larger than container', () => {
			const action = createAction({
				imageWidth: 800,
				imageHeight: 600,
				containerWidth: 400,
				containerHeight: 300,
				initialScale: 1,
			});
			// Image 800x600 at scale 1 is larger than container 400x300
			// Pan should be constrained but not centered
			expect(lastState.scale).toBe(1);
			action.destroy();
		});
	});

	describe('update', () => {
		it('applies new options', () => {
			const action = createAction({ maxScale: 2 });
			// Update maxScale to 10
			action.update({
				onUpdate: (state: any) => { lastState = state; },
				maxScale: 10,
				imageWidth: 800, imageHeight: 600,
				containerWidth: 400, containerHeight: 300,
			});
			// Zoom beyond old limit
			for (let i = 0; i < 50; i++) {
				node.dispatchEvent(new WheelEvent('wheel', {
					deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
				}));
			}
			expect(lastState.scale).toBeGreaterThan(2);
			expect(lastState.scale).toBeLessThanOrEqual(10);
			action.destroy();
		});
	});

	describe('destroy', () => {
		it('removes event listeners', () => {
			const spy = vi.fn();
			const action = createAction({ onUpdate: spy });
			const callCount = spy.mock.calls.length;
			action.destroy();
			node.dispatchEvent(new WheelEvent('wheel', {
				deltaY: -100, clientX: 200, clientY: 150, bubbles: true,
			}));
			expect(spy.mock.calls.length).toBe(callCount);
		});
	});
});
