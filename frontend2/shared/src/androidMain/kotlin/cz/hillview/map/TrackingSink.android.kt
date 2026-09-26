package cz.hillview.map

import android.content.Context
import cz.hillview.plugin.GeoTrackingManager

/**
 * The funnel's Android half: elections and rows land in the shared tracking
 * tables, through the one process-wide [GeoTrackingManager] the GeoEngine
 * also writes through.
 *
 * Only USER-set values reach the write methods — the engine's own streams
 * are excluded by `engineOwnsSource` inside the funnel, because it already
 * recorded them at sensor rate against their own timestamps.
 */
class RoomTrackingSink(context: Context) : TrackingSink {

    private val geo = GeoTrackingManager.get(context)

    override fun electBearingSource(source: String) {
        geo.setElectedBearingSource(source)
    }

    override fun electLocationSource(source: String) {
        geo.setElectedLocationSource(source)
    }

    override fun writeBearingRow(
        bearing: Double,
        source: String,
        detail: String,
        accuracyLevel: Int?,
        pitch: Double?,
        roll: Double?,
        now: Long,
    ) {
        // storeBearingNamed, not storeOrientationSensorData: that one models a
        // SENSOR SAMPLE and so demands a pitch and a roll, which a hand-set
        // bearing does not have. This used to satisfy it with `0f` for both —
        // a phone held perfectly level, written as measurement and
        // indistinguishable in the table from one that really was. The live
        // attitude arrives here from the one state when it is fresh, and null
        // when there is nothing to say.
        //
        // magneticHeading likewise: a manual bearing has no magnetic reading,
        // and copying the bearing into it (as this did) invented a compass
        // that agreed exactly with the hand that overrode it.
        geo.storeBearingNamed(
            timestamp = now,
            trueHeading = bearing.toFloat(),
            source = source,
            detail = detail,
            magneticHeading = null,
            accuracyLevel = accuracyLevel,
            pitch = pitch?.toFloat(),
            roll = roll?.toFloat(),
        )
    }

    override fun writeLocationRow(
        latitude: Double,
        longitude: Double,
        source: String,
        detail: String,
        now: Long,
    ) {
        geo.storeLocationNamed(
            timestamp = now,
            latitude = latitude,
            longitude = longitude,
            source = source,
            detail = detail,
        )
    }
}
