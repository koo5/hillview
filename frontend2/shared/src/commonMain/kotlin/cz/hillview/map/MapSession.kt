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

    /**
     * "I am at the map position, not at my fix" — the Tauri parked-map
     * semantic, but claimable only through an explicit accept: panning by
     * itself is exploration and never changes what captures record. While
     * claimed, captures geotag from the (live) map centre, tagged
     * location_source "manual", and the degraded shutter tone sounds.
     *
     * Session-only, like the rest of tracking: every app start begins with
     * GPS priority.
     */
    private val _manualPositionClaimed = MutableStateFlow(false)
    val manualPositionClaimed: StateFlow<Boolean> = _manualPositionClaimed.asStateFlow()

    fun claimManualPosition() {
        _manualPositionClaimed.value = true
        _locationTracking.value = LocationTracking.Background
    }

    fun setLocationTracking(value: LocationTracking) {
        _locationTracking.value = value
        // Taking tracking anywhere but BACKGROUND withdraws the claim —
        // ACTIVE means "follow me again", OFF means "no position at all".
        if (value != LocationTracking.Background) {
            _manualPositionClaimed.value = false
        }
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
        // A *claimed* manual position survives entering capture — the
        // whole point of the accept gate is that a surviving claim is
        // deliberate by construction. The clean-ACTIVE re-arm exists to
        // kill STALE background flags (the stuck-half-blue regression),
        // and a gated claim cannot be stale.
        if (!_manualPositionClaimed.value) {
            _locationTracking.value = LocationTracking.Active
        }
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
