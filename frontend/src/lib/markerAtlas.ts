/**
 * Optimized marker rendering system using pre-generated arrow sprites
 * Separates directional arrows from bearing diff colors for maximum efficiency
 */

import { normalizeBearing } from './utils/bearingUtils';

export interface ArrowAtlasConfig {
  bearingStep: number;  // Degrees between arrow orientations (e.g., 15°)
  arrowSize: number;    // Size of each arrow sprite in pixels
  strokeWidth: number;  // Arrow outline width
}

export class ArrowAtlas {
  private canvas: HTMLCanvasElement;
  private dataUrl: string | null = null;
  private config: ArrowAtlasConfig;
  private orientationCount: number;

  constructor(config: ArrowAtlasConfig = {
    bearingStep: 15,
    arrowSize: 32,
    strokeWidth: 2
  }) {
    this.config = config;
    this.orientationCount = Math.ceil(360 / config.bearingStep);
    this.canvas = document.createElement('canvas');
    this.generateAtlas();
  }

  private generateAtlas(): void {
    const { arrowSize, strokeWidth } = this.config;
    
    // Create horizontal atlas: all arrows in a single row
    this.canvas.width = arrowSize * this.orientationCount;
    this.canvas.height = arrowSize;
    
    const ctx = this.canvas.getContext('2d')!;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // Generate each arrow orientation
    for (let i = 0; i < this.orientationCount; i++) {
      const bearing = i * this.config.bearingStep;
      const x = i * arrowSize;
      
      this.renderArrowAt(ctx, x, 0, bearing, arrowSize, strokeWidth);
    }
    
    // Cache the data URL for CSS background-image
    this.dataUrl = this.canvas.toDataURL('image/png');
    console.log(`Generated arrow atlas: ${this.orientationCount} orientations, ${this.canvas.width}x${this.canvas.height}px`);
  }

  private renderArrowAt(
    ctx: CanvasRenderingContext2D, 
    x: number, 
    y: number, 
    bearing: number, 
    size: number, 
    strokeWidth: number
  ): void {
    const centerX = x + size / 2;
    const centerY = y + size / 2;
    const radius = size * 0.35; // Arrow length from center
    
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate((bearing * Math.PI) / 180);

    // Draw arrow shape - simple triangle pointing up
    ctx.beginPath();
    ctx.moveTo(0, -radius * 0.8);           // Tip
    ctx.lineTo(-radius * 0.3, radius * 0.4); // Left base
    ctx.lineTo(radius * 0.3, radius * 0.4);  // Right base
    ctx.closePath();

    // Fill with white (will be masked by bearing circle behind)
    ctx.fillStyle = 'white';
    ctx.fill();
    
    // Black outline for visibility
    ctx.strokeStyle = 'black';
    ctx.lineWidth = strokeWidth;
    ctx.stroke();

    ctx.restore();
  }

  /**
   * Get the background-position CSS for a specific bearing
   */
  getBackgroundPosition(bearing: number): string {
    const normalizedBearing = normalizeBearing(bearing);
    const index = Math.round(normalizedBearing / this.config.bearingStep) % this.orientationCount;
    const offsetX = index * this.config.arrowSize;
    return `-${offsetX}px 0px`;
  }

  /**
   * Get the data URL for the atlas image
   */
  getDataUrl(): string {
    return this.dataUrl || this.canvas.toDataURL('image/png');
  }

  /**
   * Get atlas dimensions for CSS
   */
  getDimensions() {
    return {
      width: this.canvas.width,
      height: this.canvas.height,
      arrowSize: this.config.arrowSize
    };
  }
}

// Singleton instance
export const arrowAtlas = new ArrowAtlas();