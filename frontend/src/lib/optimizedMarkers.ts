import L from 'leaflet';
import {arrowAtlas} from './markerAtlas';
import type {PhotoData} from './types/photoTypes';
import {photoInFront} from './mapState';
import {get, writable} from 'svelte/store';
import {app} from "$lib/data.svelte";
import {getBearingColor} from './utils/bearingUtils';

export interface OptimizedMarkerOptions {
	enablePooling: boolean;
	maxPoolSize: number;
	enableSelection: boolean;
	onMarkerClick?: (photo: PhotoData) => void;
}

const bearingDiffColorsUpdateIntervalInCaptureMode = 3000; // ms
const bearingDiffColorsUpdateIntervalInNavigationMode = 300; // ms

export const bearingDiffColorsUpdateInterval = writable(100); // ms
app.subscribe(value => {
	bearingDiffColorsUpdateInterval.set(value?.activity === 'capture' ? bearingDiffColorsUpdateIntervalInCaptureMode : bearingDiffColorsUpdateIntervalInNavigationMode);
});

/**
 * Optimized marker system using separated visual elements:
 * - Pre-rendered arrow sprites for direction
 * - CSS-colored circles for bearing diff visualization
 * - Marker pooling for performance
 */
export class OptimizedMarkerSystem {
	private options: OptimizedMarkerOptions;
	private markerPool: L.Marker[] = [];
	private activeMarkers: L.Marker[] = [];
	private atlasDataUrl: string;
	private atlasDimensions: any;
	private currentSelectedMarker: L.Marker | null = null;

	constructor(options: OptimizedMarkerOptions = {
		enablePooling: true,
		maxPoolSize: 2000,
		enableSelection: true,
		onMarkerClick: undefined
	}) {
		this.options = options;
		this.atlasDataUrl = arrowAtlas.getDataUrl();
		this.atlasDimensions = arrowAtlas.getDimensions();

		// Pre-warm the marker pool
		if (options.enablePooling) {
			this.prewarmPool(100);
		}

		// Subscribe to photoInFront changes for automatic selection updates
		photoInFront.subscribe(newPhotoInFront => {
			this.updateSelectedMarker(newPhotoInFront);
		});
	}

	/**
	 * Create optimized marker with separated visual elements
	 */
	createOptimizedMarker(photo: PhotoData): L.Marker {
		const marker = this.getPooledMarker() || new L.Marker([0, 0], { interactive: true });

		// Update marker position (will be adjusted with CSS transform for bearing offset)
		marker.setLatLng(photo.coord);

		// Create the separated visual elements
		const icon = this.createSeparatedIcon(photo);
		marker.setIcon(icon);

		const currentPhotoInFront = get(photoInFront);
		const isSelected = currentPhotoInFront && photo.id === currentPhotoInFront.id && (get(app).activity != 'capture')

		// Apply selection styling and store reference
		if (isSelected) {
			this.applySelectedStyling(marker);
			this.currentSelectedMarker = marker;
		}

		// Store photo data for updates
		(marker as any)._photoData = photo;

		return marker;
	}

	/**
	 * Create icon with separated arrow and bearing circle
	 */
	private createSeparatedIcon(photo: PhotoData): L.DivIcon {
		const currentPhotoInFront = get(photoInFront);
		const isSelected = ((currentPhotoInFront && photo.id === currentPhotoInFront.id) || false) && (get(app).activity != 'capture')
		const {arrowSize} = this.atlasDimensions;
		const data = `data-testid="photo-marker-${photo.id}"
             data-photo-id="${photo.id}"
             data-source="${photo.source?.id || 'unknown'}"
             data-is-placeholder="${photo.is_placeholder || false}"`;

		return L.divIcon({
			className: 'optimized-photo-marker',
			html: this.markerDivsHtml(
					photo.bearing,
					photo.bearing_color,
					isSelected,
					photo.source?.color,
					data,
					12,
					photo.id
				),
			iconSize: [arrowSize, arrowSize],
			iconAnchor: [arrowSize / 2, arrowSize / 2]
		});
	}


	markerDivsHtml(
		bearing: number = 0,
		bearingColor?: string,
		isSelected: boolean = false,
		sourceColor?: string,
		data: string = '',
		offsetPixels: number = 0,
		photoId?: string
	): string {

		const {arrowSize} = this.atlasDimensions;

		// Determine sizes based on zoom and selection
		const circleSize = isSelected ? arrowSize * 1 : arrowSize * 0.6;
		const arrowScale = isSelected ? 1.2 : 1.0;
		const strokeWidth = isSelected ? 3 : 1;

		// Calculate bearing offset in pixels (forward direction)
		const bearingRad = (bearing * Math.PI) / 180;
		const offsetX = offsetPixels * Math.sin(bearingRad);
		const offsetY = -offsetPixels * Math.cos(bearingRad); // negative because CSS Y increases downward

		let color = bearingColor || '#9E9E9E';

		const backgroundPos = arrowAtlas.getBackgroundPosition(bearing);

		return `<div class="marker-container"
				 ` + data + `
				 style="
				   width: ${arrowSize}px;
				   height: ${arrowSize}px;
				   transform: translate(${offsetX.toFixed(1)}px, ${offsetY.toFixed(1)}px);
				 ">

			  <!-- Bearing diff circle (background) -->
			  <div class="bearing-circle ${isSelected ? 'selected' : ''}"
				   style="
					 background-color: ${color};
					 width: ${circleSize}px;
					 height: ${circleSize}px;
					 border: ${strokeWidth}px solid ${sourceColor || '#666'};
					 opacity: 0.8;
				   "></div>

			  <!-- Direction arrow (foreground) -->
			  <div class="direction-arrow"
				   style="
					 background-image: url(${this.atlasDataUrl});
					 background-position: ${backgroundPos};
					 background-size: ${this.atlasDimensions.width}px ${this.atlasDimensions.height}px;
					 width: ${arrowSize}px;
					 height: ${arrowSize}px;
					 transform: scale(${arrowScale});
					 opacity: 0.7;
				   "></div>
		</div>`;
	}


	/**
	 * Efficiently update only the colors of existing markers (bearing changes only)
	 * This is called when bearing changes but photo positions haven't changed
	 */
	updateMarkerColors(markers: L.Marker[], currentBearing: number): void {
		//console.log('Updating marker bearing colors for ', currentBearing, 'on', markers.length, 'markers');
		const startTime = performance.now();
		let updatedCount = 0;

		markers.forEach(marker => {
			if (!marker) return; // Skip undefined/null markers
			const photoData = (marker as any)._photoData as PhotoData;
			if (!photoData) return;

			// Recalculate bearing diff color
			const bearingDiff = this.calculateAbsBearingDiff(photoData.bearing, currentBearing);
			const bearingColor = getBearingColor(bearingDiff);

			// Update only the circle color (no DOM restructure)
			const element = marker.getElement();
			if (element) {
				const circle = element.querySelector('.bearing-circle') as HTMLElement;
				if (circle && circle.style.backgroundColor !== bearingColor) {
					circle.style.backgroundColor = bearingColor;
					//console.log(`Updated marker ${photoData.id} bearing color to ${bearingColor}`);
					updatedCount++;
				}
			}
		});

		const processingTime = performance.now() - startTime;
		if (processingTime > 2) { // Only log if it takes more time
			console.log(`OptimizedMarkers: Updated ${updatedCount}/${markers.length} marker colors in ${processingTime.toFixed(1)}ms`);
		}
	}

	/**
	 * Ultra-fast bearing color update using requestAnimationFrame batching
	 * Optimized for real-time bearing changes (compass, dragging)
	 */
	private rafId: number | null = null;
	private pendingBearingUpdate: number | null = null;
	private pendingBearingUpdateTimeout: ReturnType<typeof setTimeout> | null = null;

	private lastVal: number | undefined = undefined;
	private lastUpdateTime: number = 0;

	scheduleColorUpdate(bearing: number): void {
		this.lastVal = bearing;

		if (this.pendingBearingUpdateTimeout) {
			console.log('Skipping scheduled bearing color update - already pendingBearingUpdateTimeout:', this.pendingBearingUpdateTimeout);
			return
		}

		const timeSinceLastUpdate = Date.now() - this.lastUpdateTime;
		if (timeSinceLastUpdate < get(bearingDiffColorsUpdateInterval)) {
			this.pendingBearingUpdateTimeout = setTimeout( this.updateColors.bind(this), get(bearingDiffColorsUpdateInterval));
			console.log('Scheduled pendingBearingUpdateTimeout in', get(bearingDiffColorsUpdateInterval), 'ms');
		} else {
			this.updateColors();
		}
	}

	updateColors() {

		this.lastUpdateTime = Date.now();
		if (this.pendingBearingUpdateTimeout) {
			console.log('clearing pendingBearingUpdateTimeout:', this.pendingBearingUpdateTimeout);
			this.pendingBearingUpdateTimeout = null;
			//console.log('cleared pendingBearingUpdateTimeout');
		}
		this.pendingBearingUpdate = this.lastVal ?? null;
		if (this.rafId !== null) return; // Already scheduled

		this.rafId = requestAnimationFrame(() => {
			if (this.pendingBearingUpdate !== null && this.activeMarkers.length > 0) {
				this.updateMarkerColors(this.activeMarkers, this.pendingBearingUpdate);
				this.pendingBearingUpdate = null;
			}
			this.rafId = null;
		});

	}

	/**
	 * Update selected marker efficiently using stored reference
	 * Only touches the old and new selected markers, not all markers
	 */
	updateSelectedMarker(newPhotoInFront: PhotoData | null): void {
		if (!this.options.enableSelection) return;

		// Remove selection from current selected marker
		if (this.currentSelectedMarker) {
			this.removeSelectedStyling(this.currentSelectedMarker);
			this.currentSelectedMarker = null;
		}

		if (get(app).activity == 'capture') return;
		// Find and select new marker
		if (newPhotoInFront) {
			for (const marker of this.activeMarkers) {
				const photoData = (marker as any)._photoData as PhotoData;
				if (photoData && photoData.id === newPhotoInFront.id) {
					this.applySelectedStyling(marker);
					this.currentSelectedMarker = marker;
					break;
				}
			}
		}

		console.log(`OptimizedMarkers: Updated selection to ${newPhotoInFront?.id || 'none'}`);
	}

	/**
	 * Update markers for new photo set with pooling
	 */
	updateMarkers(map: L.Map, photos: PhotoData[]): L.Marker[] {

		////console.log(`OptimizedMarkerSystem: updateMarkers called with ${photos.length} photos`);
		////console.log(`OptimizedMarkerSystem: current activeMarkers count: ${this.activeMarkers.length}`);

		// Return unused markers to pool
		this.returnMarkersToPool();
		//console.log(`OptimizedMarkerSystem: after returnMarkersToPool, activeMarkers count: ${this.activeMarkers.length}`);

		// Create/reuse markers for new photos
		this.activeMarkers = photos.map((photo, index) => {
			const marker = this.createOptimizedMarker(photo);
			marker.addTo(map);

			return marker;
		});

		//console.log(`OptimizedMarkerSystem: Created ${this.activeMarkers.length} markers, added to map`);
		return this.activeMarkers;
	}

	/**
	 * Get marker from pool or create new one
	 */
	private getPooledMarker(): L.Marker | null {
		if (!this.options.enablePooling || this.markerPool.length === 0) {
			return null;
		}

		return this.markerPool.pop()!;
	}

	/**
	 * Return markers to pool for reuse
	 */
	private returnMarkersToPool(): void {
		//console.log(`OptimizedMarkerSystem: returnMarkersToPool called, activeMarkers: ${this.activeMarkers.length}, poolSize: ${this.markerPool.length}`);

		// Clear selected marker reference
		this.currentSelectedMarker = null;

		if (!this.options.enablePooling) {
			// If not pooling, just remove markers
			//console.log(`OptimizedMarkerSystem: pooling disabled, removing ${this.activeMarkers.length} markers`);
			this.activeMarkers.forEach(marker => marker && marker.remove());
			this.activeMarkers = [];
			return;
		}

		// Move active markers back to pool
		this.activeMarkers.forEach(marker => {
			if (!marker) return;
			marker.off('click'); // Remove click handlers
			marker.remove();

			// Clean up marker state
			delete (marker as any)._photoData;

			// Add to pool if under limit
			if (this.markerPool.length < this.options.maxPoolSize) {
				this.markerPool.push(marker);
			}
		});

		this.activeMarkers = [];
		//console.log(`OptimizedMarkerSystem: returnMarkersToPool complete, activeMarkers: ${this.activeMarkers.length}, poolSize: ${this.markerPool.length}`);
	}

	/**
	 * Pre-warm the marker pool
	 */
	private prewarmPool(count: number): void {
		for (let i = 0; i < count; i++) {
			this.markerPool.push(new L.Marker([0, 0], { interactive: true }));
		}
	}

	/**
	 * Apply selected state styling to a marker
	 */
	private applySelectedStyling(marker: L.Marker): void {
		marker.setZIndexOffset(1000000);

		const element = marker.getElement();
		if (element) {
			const circle = element.querySelector('.bearing-circle');
			if (circle) {
				circle.classList.add('selected');
				const arrowSize = this.atlasDimensions.arrowSize;
				(circle as HTMLElement).style.width = `${arrowSize * 1}px`;
				(circle as HTMLElement).style.height = `${arrowSize * 1}px`;
				(circle as HTMLElement).style.borderWidth = '2px';
			}
			const arrow = element.querySelector('.direction-arrow');
			if (arrow) {
				(arrow as HTMLElement).style.transform = 'scale(1.1)';
			}
		}
	}

	/**
	 * Remove selected state styling from a marker
	 */
	private removeSelectedStyling(marker: L.Marker): void {
		marker.setZIndexOffset(0);

		const element = marker.getElement();
		if (element) {
			const circle = element.querySelector('.bearing-circle');
			if (circle) {
				circle.classList.remove('selected');
				const arrowSize = this.atlasDimensions.arrowSize;
				(circle as HTMLElement).style.width = `${arrowSize * 0.6}px`;
				(circle as HTMLElement).style.height = `${arrowSize * 0.6}px`;
				(circle as HTMLElement).style.borderWidth = '1px';
			}
			const arrow = element.querySelector('.direction-arrow');
			if (arrow) {
				(arrow as HTMLElement).style.transform = 'scale(1.0)';
			}
		}
	}

	/**
	 * Calculate absolute bearing difference
	 */
	private calculateAbsBearingDiff(bearing1: number, bearing2: number): number {
		const diff = Math.abs(bearing1 - bearing2);
		return Math.min(diff, 360 - diff);
	}


	/**
	 * Cleanup resources
	 */
	destroy(): void {
		this.returnMarkersToPool();
		this.markerPool.forEach(marker => marker && marker.remove());
		this.markerPool = [];
	}

	/**
	 * Get performance statistics
	 */
	getStats() {
		return {
			activeMarkers: this.activeMarkers.length,
			pooledMarkers: this.markerPool.length,
			totalMarkers: this.activeMarkers.length + this.markerPool.length
		};
	}

	/**
	 * Set the marker click callback (useful for setting after construction)
	 */
	setOnMarkerClick(callback: ((photo: PhotoData) => void) | undefined) {
		this.options.onMarkerClick = callback;
	}
}

// Global instance for use in Map.svelte
export const optimizedMarkerSystem = new OptimizedMarkerSystem();

/**
 * Set up event delegation for marker clicks on a map container
 * This is more robust than inline onclick handlers (works in production builds)
 */
export function setupMarkerClickDelegation(mapContainer: HTMLElement) {
	const handleClick = (e: Event) => {
		const target = e.target as HTMLElement;
		console.log('OptimizedMarkers: Click detected on', target.className, target);

		// Find the marker container that was clicked
		const markerContainer = target.closest('.marker-container[data-photo-id]') as HTMLElement;
		console.log('OptimizedMarkers: Marker container found:', markerContainer);

		if (markerContainer) {
			e.stopPropagation();
			const photoId = markerContainer.getAttribute('data-photo-id');
			console.log('OptimizedMarkers: Photo ID:', photoId);

			if (photoId) {
				// Find the photo in active markers and trigger callback
				for (const marker of optimizedMarkerSystem['activeMarkers']) {
					const photoData = (marker as any)._photoData as PhotoData;
					if (photoData && photoData.id === photoId) {
						const callback = optimizedMarkerSystem['options'].onMarkerClick;
						console.log('OptimizedMarkers: Found photo, callback:', callback ? 'exists' : 'missing');
						if (callback) {
							callback(photoData);
						}
						break;
					}
				}
			}
		}
	};

	console.log('OptimizedMarkers: Setting up event delegation on', mapContainer);
	mapContainer.addEventListener('click', handleClick, true); // Use capture phase
	mapContainer.addEventListener('touchend', (e: TouchEvent) => {
		const target = e.target as HTMLElement;
		const markerContainer = target.closest('.marker-container[data-photo-id]') as HTMLElement;
		if (markerContainer) {
			e.preventDefault();
			handleClick(e);
		}
	}, true); // Use capture phase
}
