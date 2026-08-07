package cz.hillview.map

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Tracking state that outlives a screen but not the process.
 *
 * The original has one screen with activities inside it, so "tracking is
 * on" simply survives moving to capture and back. Here the map is its own
 * destination, and keeping this in the composition meant every trip through
 * capture silently reset it — which is exactly the state the suites assert
 * about across that boundary.
 *
 * Not persisted, deliberately: `compassEnabled` and `gpsOrientationEnabled`
 * are not persisted in the original either, so every run of the app starts
 * with tracking off.
 */
class MapSession {
    private val _locationTracking = MutableStateFlow(LocationTracking.Off)
    val locationTracking: StateFlow<LocationTracking> = _locationTracking.asStateFlow()

    private val _bearingTrackingWanted = MutableStateFlow(false)
    val bearingTrackingWanted: StateFlow<Boolean> = _bearingTrackingWanted.asStateFlow()

    fun setLocationTracking(value: LocationTracking) {
        _locationTracking.value = value
    }

    fun setBearingTrackingWanted(value: Boolean) {
        _bearingTrackingWanted.value = value
    }

    /**
     * Entering capture arms a **clean** ACTIVE, and bearing tracking with
     * it. Clean is the whole point: the regression this reproduces left the
     * background flag set, which the suite describes as leaving "the button
     * stuck half-blue, GPS still logging '-background', and captures
     * recording the live fix only as alt_location".
     */
    fun onEnterCapture() {
        _locationTracking.value = LocationTracking.Active
        _bearingTrackingWanted.value = true
    }

    /**
     * Leaving capture stands bearing tracking down, as the contract says.
     * Location tracking is left alone — nothing in the original turns it off
     * here, and the user's last choice of it is still their choice.
     */
    fun onLeaveCapture() {
        _bearingTrackingWanted.value = false
    }
}
