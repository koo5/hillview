import L from 'leaflet';
import {arrowAtlas} from './markerAtlas';
import type {PhotoData} from './types/photoTypes';
import {photoInFront, bearingState} from './mapState';
import {get} from 'svelte/store';

export interface OptimizedMarkerOptions {
	enablePooling: boolean;
	maxPoolSize: number;
	enableSelection: boolean;
}

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

	constructor(options: OptimizedMarkerOptions = {
		enablePooling: true,
		maxPoolSize: 2000,
		enableSelection: true
	}) {
		this.options = options;
		this.atlasDataUrl = arrowAtlas.getDataUrl();
		this.atlasDimensions = arrowAtlas.getDimensions();

		// Pre-warm the marker pool
		if (options.enablePooling) {
			this.prewarmPool(100);
		}
	}

	/**
	 * Create optimized marker with separated visual elements
	 */
	createOptimizedMarker(photo: PhotoData): L.Marker {
		const marker = this.getPooledMarker() || new L.Marker([0, 0]);

		// Update marker position
		marker.setLatLng(photo.coord);

		// Create the separated visual elements
		const icon = this.createSeparatedIcon(photo);
		marker.setIcon(icon);

		// Store photo data for updates
		(marker as any)._photoData = photo;

		return marker;
	}

	/**
	 * Create icon with separated arrow and bearing circle
	 */
	private createSeparatedIcon(photo: PhotoData): L.DivIcon {
		const {arrowSize} = this.atlasDimensions;
		const backgroundPos = arrowAtlas.getBackgroundPosition(photo.bearing);
		const currentPhotoInFront = get(photoInFront);
		const isSelected = currentPhotoInFront && photo.id === currentPhotoInFront.id;

		// Determine sizes based on zoom and selection
		const circleSize = isSelected ? arrowSize * 0.8 : arrowSize * 0.6;
		const arrowScale = isSelected ? 1.2 : 1.0;
		const strokeWidth = isSelected ? 3 : 1;

		return L.divIcon({
			className: 'optimized-photo-marker',
			html: `
        <div class="marker-container" style="width: ${arrowSize}px; height: ${arrowSize}px;">
          <!-- Bearing diff circle (background) -->
          <div class="bearing-circle ${isSelected ? 'selected' : ''}"
               style="
                 background-color: ${photo.bearing_color || '#9E9E9E'};
                 width: ${circleSize}px;
                 height: ${circleSize}px;
                 border: ${strokeWidth}px solid ${photo.source?.color || '#666'};
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
               "></div>
        </div>
      `,
			iconSize: [arrowSize, arrowSize],
			iconAnchor: [arrowSize / 2, arrowSize / 2]
		});
	}

	/**
	 * Efficiently update only the colors of existing markers (bearing changes only)
	 * This is called when bearing changes but photo positions haven't changed
	 */
	updateMarkerColors(markers: L.Marker[], currentBearing: number): void {
		const startTime = performance.now();
		let updatedCount = 0;

		markers.forEach(marker => {
			if (!marker) return; // Skip undefined/null markers
			const photoData = (marker as any)._photoData as PhotoData;
			if (!photoData) return;

			// Recalculate bearing diff color
			const bearingDiff = this.calculateAbsBearingDiff(photoData.bearing, currentBearing);
			const bearingColor = this.getBearingColor(bearingDiff);

			// Update only the circle color (no DOM restructure)
			const element = marker.getElement();
			if (element) {
				const circle = element.querySelector('.bearing-circle') as HTMLElement;
				if (circle && circle.style.backgroundColor !== bearingColor) {
					circle.style.backgroundColor = bearingColor;
					updatedCount++;
				}
			}
		});

		const processingTime = performance.now() - startTime;
		if (processingTime > 5) { // Only log if it takes more than 5ms
			console.log(`OptimizedMarkers: Updated ${updatedCount}/${markers.length} marker colors in ${processingTime.toFixed(1)}ms`);
		}
	}

	/**
	 * Ultra-fast bearing color update using requestAnimationFrame batching
	 * Optimized for real-time bearing changes (compass, dragging)
	 */
	private rafId: number | null = null;
	private pendingBearingUpdate: number | null = null;
	private pendingBearingUpdateTimeout: returnType<typeof setTimeout> | null = null;

	private lastVal: number | undefined = undefined;
	scheduleColorUpdate(bearing: number): void {
		lastVal = bearing;
		if (this.pendingBearingUpdateTimeout) {
			return
		}

		this.pendingBearingUpdateTimeout = setTimeout(() => {
			this.pendingBearingUpdateTimeout = null;

			this.pendingBearingUpdate = lastVal;

			if (this.rafId !== null) return; // Already scheduled

			this.rafId = requestAnimationFrame(() => {
				if (this.pendingBearingUpdate !== null && this.activeMarkers.length > 0) {
					this.updateMarkerColors(this.activeMarkers, this.pendingBearingUpdate);
					this.pendingBearingUpdate = null;
				}
				this.rafId = null;
			});


		}, 100);
	}

	/**
	 * Update markers for new photo set with pooling
	 */
	updateMarkers(map: L.Map, photos: PhotoData[]): L.Marker[] {
		// Return unused markers to pool
		this.returnMarkersToPool();

		// Create/reuse markers for new photos
		this.activeMarkers = photos.map((photo, index) => {
			const marker = this.createOptimizedMarker(photo);
			marker.addTo(map);

			// Debug: Log first few markers and check z-index
			if (index < 5) {
				console.log(`Created marker ${index} at [${photo.coord.lat}, ${photo.coord.lng}]`, marker);

				// Check the z-index after adding to map
				setTimeout(() => {
					const element = marker.getElement();
					if (element) {
						const computedStyle = getComputedStyle(element);
						const zIndex = computedStyle.zIndex;
						console.log(`🢄Marker ${index} z-index: ${zIndex}, element:`, element);
					}
				}, 100);
			}

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
		if (!this.options.enablePooling) {
			// If not pooling, just remove markers
			this.activeMarkers.forEach(marker => marker && marker.remove());
			this.activeMarkers = [];
			return;
		}

		// Move active markers back to pool
		this.activeMarkers.forEach(marker => {
			if (!marker) return;
			marker.remove();

			// Clean up marker state
			delete (marker as any)._photoData;

			// Add to pool if under limit
			if (this.markerPool.length < this.options.maxPoolSize) {
				this.markerPool.push(marker);
			}
		});

		this.activeMarkers = [];
	}

	/**
	 * Pre-warm the marker pool
	 */
	private prewarmPool(count: number): void {
		for (let i = 0; i < count; i++) {
			this.markerPool.push(new L.Marker([0, 0]));
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
	 * Convert bearing difference to color
	 */
	private getBearingColor(absBearingDiff: number): string {
		if (absBearingDiff === null || absBearingDiff === undefined) return '#9E9E9E';
		return `hsl(${Math.round(100 - absBearingDiff / 2)}, 100%, 70%)`;
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
}

// Global instance for use in Map.svelte
export const optimizedMarkerSystem = new OptimizedMarkerSystem();
