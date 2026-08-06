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
    val source: String = "map",
    val ts: Long? = null,
)

data class BearingState(
    val bearing: Double = 141.0,
    val source: String = "map",
    val photoUid: String? = null,
    val accuracyLevel: Int? = null,
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
) {
    private val _spatial = MutableStateFlow(initialSpatial)
    val spatial: StateFlow<SpatialState> = _spatial.asStateFlow()

    private val _bearing = MutableStateFlow(initialBearing)
    val bearing: StateFlow<BearingState> = _bearing.asStateFlow()

    /**
     * Dedups ignoring [SpatialState.ts] — this is the terminal break of the
     * map→store→map ping-pong. Returns true when it actually wrote.
     */
    fun updateSpatial(
        latitude: Double = _spatial.value.latitude,
        longitude: Double = _spatial.value.longitude,
        zoom: Double = _spatial.value.zoom,
        range: Double = _spatial.value.range,
        source: String = "map",
        setTimestamp: Boolean = true,
        now: Long,
    ): Boolean {
        val old = _spatial.value
        val candidate = old.copy(
            latitude = latitude, longitude = longitude, zoom = zoom,
            range = range, source = source,
        )
        if (candidate.copy(ts = null) == old.copy(ts = null)) return false
        _spatial.value = candidate.copy(ts = if (setTimestamp) now else old.ts)
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
        setTimestamp: Boolean = true,
        now: Long,
    ) {
        val old = _bearing.value
        _bearing.value = BearingState(
            bearing = normalizeBearing(bearing),
            source = source,
            photoUid = photoUid,
            accuracyLevel = accuracyLevel,
            ts = if (setTimestamp) now else old.ts,
        )
    }

    /** Preserves source, photoUid and accuracy unless overridden. */
    fun updateBearingByDiff(diff: Double, source: String? = null, now: Long) {
        val old = _bearing.value
        _bearing.value = old.copy(
            bearing = normalizeBearing(old.bearing + diff),
            source = source ?: old.source,
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
