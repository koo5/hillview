package cz.hillview.map

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Map state, ported from the Tauri app's mapState.ts. See
 * docs/tauri-map-ui-contract.md — the semantics here are deliberate, not
 * incidental, and were read out of the working app.
 */

/**
 * [range] is metres-per-70-screen-pixels, read back from the map, not a
 * setting: it draws the selection circle and decides what counts as in
 * range. [ts] marks the last *intentional* update and is left null on a
 * blank first run so automatic navigation may steer.
 */
data class SpatialState(
    val latitude: Double = 50.11692048550961,
    val longitude: Double = 14.488374441862108,
    val zoom: Double = 10.0,
    val range: Double = 1000.0,
    /**
     * Which way is up, in degrees clockwise, as set by a two-finger rotate.
     * Part of spatial state rather than the bearing: it says how the map is
     * held, not where the user is looking. A rotated map that silently
     * snapped back north-up on resume would read as the gesture being lost.
     */
    val orientation: Double = 0.0,
    val source: String = "map",
    val ts: Long? = null,
)

/**
 * Where the user is facing, and everything that came with that answer.
 *
 * [magneticDeg] and [pitch] live HERE, beside the bearing, rather than being
 * read off the sensor at the moment they are needed. A photo records all
 * three, and read separately they are three different instants — worse, when
 * the elected bearing is a manual claim, a car-mode course or a photo the
 * user turned to, a pitch sampled straight from the compass stack belongs to
 * a different answer entirely. One state, written in one call, so a row
 * cannot disagree with itself. Sources that do not measure them write null,
 * which is the truth about those sources.
 */
data class BearingState(
    val bearing: Double = 141.0,
    val source: String = "map",
    val photoUid: String? = null,
    val accuracyLevel: Int? = null,
    /** Uncorrected compass heading, when the elected source has one. */
    val magneticDeg: Double? = null,
    /** Tilt, when the elected source has one — null is "not recorded". */
    val pitch: Double? = null,
    val ts: Long? = null,
)

/** OFF / ACTIVE / BACKGROUND, mutually exclusive (see the contract). */
enum class LocationTracking { Off, Active, Background }

/** What the receiver's fix is currently FOR. */
enum class FixRole {
    /** No fixes at all. */
    Off,

    /** The fix is what a photo records. */
    Primary,

    /** The map position is what a photo records; the fix rides along as
     *  `alt_location`, tagged `gps-background`. */
    Alternate,
}

/**
 * What the location button is saying, which is a question about the
 * ELECTION and not about whether the map is following.
 *
 * The distinction only exists here. The original castles the two position
 * streams the moment the map is panned (`enterBackgroundTracking` →
 * `setElectedLocationSource('manual')`), so there "panned" and "the fix is
 * demoted" are one event and one colour can mean both. frontend2 waits for
 * the pill's accepted claim, which puts a whole state between them —
 * exploring, where the map is parked but the FIX IS STILL WHAT A PHOTO
 * RECORDS. The button inherited the original's rule and so went half-lit on
 * the pan, announcing a demotion that had not happened (user-caught,
 * 2026-09-11).
 *
 * That the map is parked is not lost by this: the claim pill stays up until
 * it is answered, and the blue GPS dot shows where the receiver says you
 * are.
 */
fun fixRole(tracking: LocationTracking, mapPositionElected: Boolean): FixRole = when {
    tracking == LocationTracking.Off -> FixRole.Off
    mapPositionElected -> FixRole.Alternate
    else -> FixRole.Primary
}

/**
 * The receiver's latest fix — the position's SECOND stream, given a home in
 * the one state (docs/one-state.md, "The position side"). Until 2026-09-09
 * this lived only in the capture pane's private subscription, because a
 * fix moving the map and a pan moving it both overwrote [SpatialState] and
 * neither was recoverable once the other had written.
 *
 * Session-scoped, deliberately: a measurement does not survive a relaunch,
 * because its age would be a day and its `gps` word a lie. [SpatialState]
 * is the other record — the map centre, persisted, as the map is.
 *
 * [elapsedRealtimeNanos] is the point of carrying the whole record rather
 * than a lat/lng pair: the stamp's fix age is measured against the
 * monotonic clock, and a pair would silently lose it. [atMs] is the same
 * instant on the wall clock, for the overlay's readout and the CSV.
 */
data class FixState(
    val latitude: Double,
    val longitude: Double,
    val altitude: Double? = null,
    val accuracyM: Float? = null,
    /** Wall-clock ms of the fix. */
    val atMs: Long,
    /** Monotonic ns of the fix — what fix age at the shutter is measured from. */
    val elapsedRealtimeNanos: Long,
    // Everything below is what the RECEIVER also said and this record used to
    // drop (2026-09-26). `PreciseLocationData` has carried all of it from the
    // start; FixState kept six fields and discarded the rest, so a photo could
    // say its position was accurate to 4 m horizontally and nothing at all
    // about the vertical — which matters, because altitude is part of a camera
    // centre. Null where the platform did not report one; that is a real
    // distinction and never a zero.
    /** Vertical error bar, metres — the altitude's accuracy, not the position's. */
    val altitudeAccuracyM: Float? = null,
    /** Ground speed, m/s. Motion at the shutter, and car mode's input. */
    val speedMps: Float? = null,
    /** Error bar on [speedMps], m/s. */
    val speedAccuracyMps: Float? = null,
    /**
     * The receiver's own COURSE — the direction of travel it derived from
     * successive fixes. Not a heading: a phone pointed sideways out of a car
     * window has a course down the road and a heading across it. Car mode
     * composes this into a bearing; it is kept raw here as well.
     */
    val courseDeg: Float? = null,
    /** Error bar on [courseDeg], degrees. */
    val courseAccuracyDeg: Float? = null,
    /**
     * Which platform provider produced it — "gps", "network", "fused". NOT
     * the app's `location_source`, which says whether the PHOTO recorded a fix
     * or the map centre. With the fused client this usually reads "fused", so
     * it discriminates less than it looks; kept because when it does say
     * "network" that fix is worthless for reconstruction and nothing else
     * would have told you.
     */
    val provider: String? = null,
)

/**
 * What the DEVICE itself was measuring, last time it said — independent of
 * which bearing source is elected.
 *
 * The orientation side's answer to what [FixState] is on the position side:
 * a second stream that must be recoverable after another source has won the
 * election. [BearingState] holds the ELECTED answer, and a manual claim, a
 * car course or a photo the user turned to all write null for pitch — which
 * is the truth about those sources, and leaves nothing at all saying how the
 * phone was actually being held at that moment.
 *
 * That gap had two visible costs. A manual bearing row reached the tracking
 * table with pitch and roll invented as `0f` — a phone held perfectly level,
 * recorded as a measurement. And roll never left the device at all: the
 * sensor stack computes it, [BearingState] has no field for it, so the photo
 * stamp could not carry it (user, 2026-09-22: "the phone should store every
 * bit of info it has, both raw and processed").
 *
 * Session-scoped like [FixState], and for the same reason: an attitude does
 * not survive a relaunch, because its age would be a day.
 *
 * **[roll] is not the camera's rotation about its optical axis.** The sensor
 * stack remaps the rotation matrix for the QUANTIZED device pose
 * (portrait / landscape-left / …) before reading pitch and roll out of it,
 * so this roll is the residual tilt within that quadrant. The absolute
 * rotation is this plus the pose, which the photo stamp records separately
 * as `deviceRotationDeg`. A consumer needs both, which is why the stamp's
 * provenance carries both.
 */
data class DeviceAttitude(
    /** Declination-corrected heading the compass itself reported. */
    val trueDeg: Double,
    /** Uncorrected compass heading — the raw half of the same reading. */
    val magneticDeg: Double,
    /** Tilt, degrees, positive up. */
    val pitch: Double,
    /** Residual roll within the quantized device pose — see above. */
    val roll: Double,
    /**
     * The MAGNETOMETER's calibration status — 0 unreliable, 1 low, 2 medium,
     * 3 high; null when Android has never reported one. It qualifies
     * [trueDeg] and [magneticDeg] only: [pitch] and [roll] come from gravity
     * and the gyro, which this says nothing about. Latched, not per-sample —
     * see `attitudeProvenanceJson` for the full set of caveats.
     *
     * Named for what it IS, not for Android's word for it. The same value
     * reaches the tracking table as `BearingEntity.accuracyLevel` and the
     * bearing state as [BearingState.accuracyLevel] — both keep the old name,
     * because one is a database column and the other its mirror, and neither
     * is worth a migration to rename. New readers should learn it here.
     */
    val magnetometerCalibration: Int? = null,
    /**
     * What the sensor that produced this sample said about ITSELF —
     * `SensorEvent.accuracy`, same 0..3 scale, null when unknown.
     *
     * [magnetometerCalibration] rates the bare magnetometer; this rates the
     * fused reading that the heading actually came from. Kept beside it
     * because they can disagree, and which one is low says whether the
     * magnetic field or the fusion was the trouble. Null from the hand-rolled
     * filters, which compose several raw sensors and rate nothing.
     */
    val fusedSensorAccuracy: Int? = null,
    /** Which fusion produced it, within the `android` source. */
    val detail: String? = null,
    /** Wall-clock ms of the sample. */
    val ts: Long,

    /**
     * This sample on `elapsedRealtimeNanos` — the clock a capture's exposure instant is
     * on, so "what was the attitude when the shutter actually opened" is answerable by
     * lookup rather than by assuming the press. 0 from producers that do not set it,
     * and a 0 simply never matches.
     */
    val elapsedNs: Long = 0L
)

/**
 * Gravity and linear acceleration, as last measured — the INERTIAL half of how
 * the phone was held, beside [DeviceAttitude]'s angular half.
 *
 * Session-scoped like the rest, and null the moment nothing is measuring it.
 */
@kotlinx.serialization.Serializable
data class DeviceMotionSample(
    /**
     * Gravity in the DEVICE frame, m/s², (x, y, z). An unambiguous "down",
     * unlike [DeviceAttitude.roll], which is a residual within the quantized
     * device pose. Two rotation degrees of freedom, straight out of the sensor.
     */
    val gravity: List<Float>? = null,
    /**
     * Acceleration with gravity REMOVED, m/s², (x, y, z). Its magnitude is how
     * hard the phone was being moved, which is the motion-blur signal; a raw
     * accelerometer sample cannot give this, because it is this plus gravity
     * and one sample cannot separate them.
     */
    val linearAcceleration: List<Float>? = null,
    /** Wall-clock ms of the sample that triggered this publication. */
    val atMs: Long,

    /** Same instant on `elapsedRealtimeNanos` — see DeviceAttitude.elapsedNs. */
    val elapsedNs: Long = 0L
)

/**
 * How stale an attitude may be and still be attached to a row or a photo it
 * did not itself produce.
 *
 * The sensor stack publishes at ~10 Hz while the compass is registered, so a
 * fresh reading is tens of milliseconds old; anything approaching this bound
 * means the sensors are paused, gone, or were never started for this mode.
 * Attaching one of those to a manual bearing would put a stale measurement
 * under a fresh timestamp, which is the same lie as the `0f` it replaces,
 * only harder to spot.
 */
const val ATTITUDE_MAX_AGE_MS = 2_000L

/** The attitude, if it is fresh enough at [now] to describe that instant. */
fun DeviceAttitude?.freshAt(now: Long): DeviceAttitude? =
    this?.takeIf { now - it.ts in 0..ATTITUDE_MAX_AGE_MS }

/**
 * Holds map state and enforces the update rules the Svelte app relies on.
 * Kept out of Compose so the rules are testable and can't drift into
 * recomposition details.
 */
class MapStateHolder(
    initialSpatial: SpatialState = SpatialState(),
    initialBearing: BearingState = BearingState(),
    /**
     * The persist boundary. These two update functions are the app's single
     * write funnel for position and heading — the analog of
     * `updateSpatialState`/`updateBearing` in the original's mapState.ts,
     * which do three jobs in ONE call: update the state, push the election,
     * and write the tracking-table row. Because the row write is a side
     * effect of the state write, a user-set value cannot end up meaning one
     * thing in the state and another in the table.
     */
    private val sink: TrackingSink = TrackingSink.Noop,
) {
    private val _spatial = MutableStateFlow(initialSpatial)
    val spatial: StateFlow<SpatialState> = _spatial.asStateFlow()

    private val _bearing = MutableStateFlow(initialBearing)
    val bearing: StateFlow<BearingState> = _bearing.asStateFlow()

    // Not persisted and not in the constructor: see FixState — a fix is a
    // measurement of THIS session, and every run starts with none.
    private val _lastFix = MutableStateFlow<FixState?>(null)
    val lastFix: StateFlow<FixState?> = _lastFix.asStateFlow()

    // Same reasoning as lastFix: a measurement of THIS session.
    private val _deviceAttitude = MutableStateFlow<DeviceAttitude?>(null)
    val deviceAttitude: StateFlow<DeviceAttitude?> = _deviceAttitude.asStateFlow()

    // The inertial half, same rules.
    private val _deviceMotion = MutableStateFlow<DeviceMotionSample?>(null)
    val deviceMotion: StateFlow<DeviceMotionSample?> = _deviceMotion.asStateFlow()

    // The last election handed to the sink, so we push on CHANGE only: these
    // funnels run at sensor rate, the election does not.
    private var lastElectedBearing: String? = null
    private var lastElectedLocation: String? = null

    /**
     * Dedups ignoring [SpatialState.ts] — this is the terminal break of the
     * map→store→map ping-pong. Returns true when it actually wrote.
     */
    fun updateSpatial(
        latitude: Double = _spatial.value.latitude,
        longitude: Double = _spatial.value.longitude,
        zoom: Double = _spatial.value.zoom,
        range: Double = _spatial.value.range,
        orientation: Double = _spatial.value.orientation,
        source: String = "map",
        setTimestamp: Boolean = true,
        now: Long,
    ): Boolean {
        val old = _spatial.value
        val candidate = old.copy(
            latitude = latitude, longitude = longitude, zoom = zoom,
            range = range, orientation = orientation, source = source,
        )
        if (candidate.copy(ts = null) == old.copy(ts = null)) return false
        _spatial.value = candidate.copy(ts = if (setTimestamp) now else old.ts)
        // A fix moving the map is the ENGINE's stream, already recorded at
        // full rate; anything else is the user placing themselves, and that
        // pan IS the act of electing the map position — so the row carries
        // its own election and cannot be stamped with the era it ends.
        if (source != "gps") {
            val table = toTableSource(source)
            elect(table.source, bearing = false)
            sink.writeLocationRow(latitude, longitude, table.source, table.detail, now)
        } else {
            elect("android", bearing = false)
        }
        return true
    }

    /**
     * The fix funnel. Every fix the engine publishes lands here, whatever
     * the tracking mode — following also moves the map through
     * [updateSpatial], exploring does not, but the RECORD is kept either
     * way, which is what lets a photo be stamped from the fix while the map
     * is parked somewhere else. No election and no table row: the engine
     * already records its own stream at full rate.
     */
    fun updateFix(fix: FixState) {
        _lastFix.value = fix
    }

    /**
     * The attitude funnel. Every compass sample lands here whatever is
     * elected — the twin of [updateFix], and like it, no election and no
     * table row: the engine already records its own stream at full rate.
     * This is the RECORD, kept so that a bearing set by hand can still say
     * how the phone was being held when the hand set it.
     */
    fun updateDeviceAttitude(attitude: DeviceAttitude) {
        _deviceAttitude.value = attitude
    }

    /** The inertial twin of [updateDeviceAttitude]; null when nothing measures it. */
    fun updateDeviceMotion(motion: DeviceMotionSample?) {
        _deviceMotion.value = motion
    }

    /**
     * The range READ-BACK — what the 70 dp circle currently means on the
     * ground, measured off the map's projection after a move or zoom. The
     * original recomputes it on every map sync (get_range, Map.svelte:651);
     * here it was never written at all, so the viewer's ring culled against
     * the constructor default (1000 m) forever while the drawn circle
     * shrank with zoom — navigation reached photos far outside the circle
     * (user-caught in gallery mode).
     *
     * Deliberately NOT [updateSpatial]: a range change is a measurement,
     * not the user placing themselves — it must not elect the map position,
     * write a tracking row, or bump the intentional-move timestamp.
     */
    fun updateRange(range: Double) {
        val old = _spatial.value
        if (range == old.range || range <= 0.0) return
        _spatial.value = old.copy(range = range)
    }

    /**
     * No dedup — every call notifies, as in the original. Note that
     * [photoUid] and [accuracyLevel] are **cleared** when not supplied:
     * that is how a compass tick drops the photo selection.
     */
    fun updateBearing(
        bearing: Double,
        source: String = "map",
        photoUid: String? = null,
        accuracyLevel: Int? = null,
        /** Only the compass has these; every other source writes null. */
        magneticDeg: Double? = null,
        pitch: Double? = null,
        setTimestamp: Boolean = true,
        now: Long,
    ) {
        val old = _bearing.value
        _bearing.value = BearingState(
            bearing = normalizeBearing(bearing),
            source = source,
            photoUid = photoUid,
            accuracyLevel = accuracyLevel,
            magneticDeg = magneticDeg,
            pitch = pitch,
            ts = if (setTimestamp) now else old.ts,
        )
        // "Whoever wrote the bearing last IS the elected source" — the
        // original's rule, and it gives "not elected while still starting up"
        // for free: a stream that has produced no reading has not called this.
        val table = toTableSource(source)
        elect(table.source, bearing = true)
        // …but only echo what the engine does not already record itself.
        if (!engineOwnsSource(source)) {
            // What the device was doing as this bearing was set. Null when
            // the sensors have nothing fresh to say (car mode with the
            // compass down, a paused stream) — null, and not the `0f` that
            // stood here until 2026-09-22, which recorded a level phone.
            val attitude = _deviceAttitude.value.freshAt(now)
            sink.writeBearingRow(
                normalizeBearing(bearing), table.source, table.detail, accuracyLevel,
                pitch = attitude?.pitch,
                roll = attitude?.roll,
                now = now,
            )
        }
    }

    private fun elect(source: String, bearing: Boolean) {
        if (bearing) {
            if (source == lastElectedBearing) return
            lastElectedBearing = source
            sink.electBearingSource(source)
        } else {
            if (source == lastElectedLocation) return
            lastElectedLocation = source
            sink.electLocationSource(source)
        }
    }

    /** Preserves source, photoUid and accuracy unless overridden. */
    /**
     * Turn the bearing by a hand-applied angle — car mode's mount offset.
     *
     * Pitch and magnetic heading do NOT survive it. Someone reaches for a
     * manual adjustment precisely when the sensors are of no use
     * (interference is the usual reason), so carrying the last sample's
     * measurements forward would attach them to a value that deliberately
     * overrode measurement — under the new source's name, where nothing
     * downstream could tell they were inherited.
     *
     * Accuracy is preserved, unlike those two, because the original does:
     * `accuracy_level ?? current.accuracy_level` (mapState.ts:513). It is
     * the compass's own quality rating and predates this state carrying any
     * measurement, so the port keeps its behaviour rather than quietly
     * improving on it — pitch and magneticDeg are fields the original never
     * had, and the rule above is what decides them.
     */
    fun updateBearingByDiff(diff: Double, source: String? = null, now: Long) {
        val old = _bearing.value
        _bearing.value = old.copy(
            bearing = normalizeBearing(old.bearing + diff),
            source = source ?: old.source,
            magneticDeg = null,
            pitch = null,
            ts = now,
        )
    }
}

fun normalizeBearing(bearing: Double): Double = ((bearing % 360) + 360) % 360

/**
 * How far off north a map orientation is, signed, in (-180, 180].
 *
 * The signed form is what a reader wants: 350° and 10° are both ten degrees
 * off, and the map's own "is it turned at all" test has to treat them the
 * same. One function so the badge that appears and the number it shows can
 * never disagree about the answer.
 */
fun offNorthDeg(mapOrientation: Double): Double {
    val normalized = normalizeBearing(mapOrientation)
    return if (normalized > 180) normalized - 360 else normalized
}

/** Shortest angular distance, signed, in (-180, 180]. */
fun angularDistance(from: Double, to: Double): Double {
    var diff = (to - from + 540) % 360 - 180
    if (diff == -180.0) diff = 180.0
    return diff
}

/** Unsigned difference used for the marker bearing colours: 0..180. */
fun absBearingDiff(a: Double, b: Double): Double {
    val diff = kotlin.math.abs(normalizeBearing(a) - normalizeBearing(b))
    return kotlin.math.min(diff, 360 - diff)
}
