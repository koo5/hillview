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
        now: Long,
    ) {
        geo.storeOrientationSensorData(
            cz.hillview.plugin.OrientationSensorData(
                magneticHeading = bearing.toFloat(),
                trueHeading = bearing.toFloat(),
                accuracyLevel = accuracyLevel ?: -1,
                pitch = 0f,
                roll = 0f,
                timestamp = now,
                source = source,
                detail = detail,
            ),
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
