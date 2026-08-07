package cz.hillview.map

import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.gestures.RotationGestureOverlay

/**
 * Two-finger rotation, reported back so the turn becomes state.
 *
 * osmdroid's [RotationGestureOverlay] turns the map but tells nobody. Left
 * like that the store never learns about the gesture, so the map would snap
 * back north-up on the next state-driven update and again on resume — the
 * same "the map ate my gesture" failure the upward pan sync fixes.
 */
class RotationSyncOverlay(
    private val map: MapView,
    private val onOrientation: (Double) -> Unit,
) : RotationGestureOverlay(map) {

    override fun onRotate(deltaAngle: Float) {
        super.onRotate(deltaAngle)
        onOrientation(map.mapOrientation.toDouble())
    }
}
