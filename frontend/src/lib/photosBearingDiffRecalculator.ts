
/**
 * DEPRECATED: This functionality is now handled by the optimizedMarkerSystem
 * in optimizedMarkers.ts with real-time CSS updates instead of store recalculation.
 * 
 * The new system uses:
 * - Pre-rendered arrow sprites (markerAtlas.ts)
 * - Separated visual elements (arrow + bearing color circle)
 * - Direct CSS color updates for bearing changes
 * - No need for store recalculation or complex state management
 */

export function triggerPhotosBearingDiffRecalculator() {
    // No-op: Functionality moved to optimizedMarkerSystem.updateMarkerColors()
    console.warn('triggerPhotosBearingDiffRecalculator is deprecated - use optimizedMarkerSystem instead');
}
