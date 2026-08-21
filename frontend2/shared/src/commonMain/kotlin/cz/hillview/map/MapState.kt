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
            sink.writeBearingRow(
                normalizeBearing(bearing), table.source, table.detail, accuracyLevel, now,
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
