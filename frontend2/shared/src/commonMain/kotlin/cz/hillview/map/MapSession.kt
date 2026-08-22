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

    /**
     * The capture pane's escape hatch: "No GPS fix — capture at the map
     * position instead". The same outcome as a claim, reached differently —
     * there is no fix to accept the map position *over*, so it needs no gate,
     * and it is withdrawn by its own button rather than by resuming follow-me.
     *
     * It lives here rather than in the capture pane because it decides what
     * gets written to the tracking tables, and that has to be answerable while
     * the pane is closed.
     */
    private val _mapPositionWithoutFix = MutableStateFlow(false)
    val mapPositionWithoutFix: StateFlow<Boolean> = _mapPositionWithoutFix.asStateFlow()

    /**
     * Whether the map position is what captures record — by either route.
     *
     * One flow, so there is a single answer to "is the map position elected"
     * and a single publisher of it to the tracking tables. Two ways in, one
     * way to read it.
     */
    private val _manualPositionElected = MutableStateFlow(false)
    val manualPositionElected: StateFlow<Boolean> = _manualPositionElected.asStateFlow()

    private fun recomputeElection() {
        _manualPositionElected.value =
            _manualPositionClaimed.value || _mapPositionWithoutFix.value
    }

    fun claimManualPosition() {
        _manualPositionClaimed.value = true
        _locationTracking.value = LocationTracking.Background
        recomputeElection()
    }

    fun setMapPositionWithoutFix(value: Boolean) {
        _mapPositionWithoutFix.value = value
        recomputeElection()
    }

    fun setLocationTracking(value: LocationTracking) {
        _locationTracking.value = value
        // Taking tracking anywhere but BACKGROUND withdraws the claim —
        // ACTIVE means "follow me again", OFF means "no position at all".
        // The no-fix hatch is left alone: it is about there being nothing to
        // follow, which resuming follow-me does not change.
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
