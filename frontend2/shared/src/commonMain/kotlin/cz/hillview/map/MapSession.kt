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
     * itself is exploration and never changes what captures record WHILE
     * THERE IS A FIX TO RECORD. While claimed, captures geotag from the
     * (live) map centre, tagged location_source "map", and the degraded
     * shutter tone sounds.
     *
     * This is the ONE way the map position is elected over a fix. There used
     * to be a second — the capture pane's "No GPS fix — capture at the map
     * position instead" hatch, with its own flag here — and it is gone
     * (2026-09-09): with no fix there is nothing to elect the map position
     * *over*, so the map centre is simply what a photo records, and no
     * button is needed to say so. See docs/one-state.md, "The position
     * side: two records, one claim".
     *
     * Session-only, like the rest of tracking: every app start begins with
     * GPS priority.
     */
    private val _manualPositionClaimed = MutableStateFlow(false)
    val manualPositionClaimed: StateFlow<Boolean> = _manualPositionClaimed.asStateFlow()

    /**
     * Whether the map position is what captures record OVER A FIX — the
     * claim, and only the claim. Kept as its own flow because it is the
     * single answer the tracking-table publisher reads; it used to combine
     * two routes and now mirrors one.
     */
    private val _manualPositionElected = MutableStateFlow(false)
    val manualPositionElected: StateFlow<Boolean> = _manualPositionElected.asStateFlow()

    private fun recomputeElection() {
        _manualPositionElected.value = _manualPositionClaimed.value
    }

    fun claimManualPosition() {
        _manualPositionClaimed.value = true
        _locationTracking.value = LocationTracking.Background
        recomputeElection()
    }

    fun setLocationTracking(value: LocationTracking) {
        _locationTracking.value = value
        // Taking tracking anywhere but BACKGROUND withdraws the claim —
        // ACTIVE means "follow me again", OFF means "no position at all".
        if (value != LocationTracking.Background) {
            _manualPositionClaimed.value = false
        }
        recomputeElection()
    }

    fun setBearingTrackingWanted(value: Boolean) {
        _bearingTrackingWanted.value = value
    }

    /**
     * What the bearing plumbing is actually DOING, as opposed to what the
     * user asked for above. It lives here rather than in the map's
     * composition because it is the status of a session-long activity and
     * because the capture pane's debug readout has to be able to see it —
     * "want ON, phase Error" is a diagnosis, and it is invisible if the
     * phase is a variable inside one screen.
     */
    private val _bearingPhase = MutableStateFlow(TrackingPhase.Inactive)
    val bearingPhase: StateFlow<TrackingPhase> = _bearingPhase.asStateFlow()

    fun setBearingPhase(value: TrackingPhase) {
        _bearingPhase.value = value
    }

    /**
     * Entering a RECORDING activity arms a **clean** ACTIVE, and bearing
     * tracking with it. Clean is the whole point: the regression this
     * reproduces left the background flag set, which the suite describes as
     * leaving "the button stuck half-blue, GPS still logging '-background',
     * and captures recording the live fix only as alt_location".
     *
     * Recording means capture OR the external-camera pane. The original has
     * only the first, so it could call this "entering capture"; here the
     * external pane records position and heading for photos another app is
     * taking, which is the same claim on the same hardware and wants the
     * same arming. Treating it as "leaving capture" is what left its
     * bearing-tracking button dark while it recorded.
     */
    fun onEnterRecording() {
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
     * Leaving recording altogether stands bearing tracking down, as the
     * contract says — capture to external is not leaving. Location tracking
     * is left alone: nothing in the original turns it off here, and the
     * user's last choice of it is still their choice.
     */
    fun onLeaveRecording() {
        _bearingTrackingWanted.value = false
    }
}
