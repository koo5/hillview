package cz.hillview.map

import android.content.Context

/**
 * Mirrors the Tauri app's `spatialState` / `bearingState` localStorage keys.
 * SharedPreferences.apply() already batches writes off the main thread, so
 * no extra debounce is needed here.
 */
class PrefsMapStateStore(context: Context) : MapStateStore {
    private val prefs = context.getSharedPreferences("hillview_map_state", Context.MODE_PRIVATE)

    override fun load(): Pair<SpatialState, BearingState>? {
        if (!prefs.contains("bearing")) return null
        val spatial = SpatialState(
            latitude = prefs.getFloat("lat", 50.1169f).toDouble(),
            longitude = prefs.getFloat("lon", 14.4884f).toDouble(),
            zoom = prefs.getFloat("zoom", 10f).toDouble(),
            orientation = prefs.getFloat("orientation", 0f).toDouble(),
            range = prefs.getFloat("range", 1000f).toDouble(),
            source = prefs.getString("spatial_source", "map") ?: "map",
            // A restored position IS prior user intent, so the timestamp
            // must come back too — it is what stops automatic navigation
            // from steering later.
            ts = prefs.getLong("spatial_ts", 0L).takeIf { it != 0L },
        )
        val bearing = BearingState(
            bearing = prefs.getFloat("bearing", 141f).toDouble(),
            source = prefs.getString("bearing_source", "map") ?: "map",
            photoUid = prefs.getString("photo_uid", null),
            accuracyLevel = prefs.getInt("accuracy", -1).takeIf { it >= 0 },
            ts = prefs.getLong("bearing_ts", 0L).takeIf { it != 0L },
        )
        return spatial to bearing
    }

    override fun save(spatial: SpatialState, bearing: BearingState) {
        prefs.edit()
            .putFloat("lat", spatial.latitude.toFloat())
            .putFloat("lon", spatial.longitude.toFloat())
            .putFloat("zoom", spatial.zoom.toFloat())
            .putFloat("orientation", spatial.orientation.toFloat())
            .putFloat("range", spatial.range.toFloat())
            .putString("spatial_source", spatial.source)
            .putLong("spatial_ts", spatial.ts ?: 0L)
            .putFloat("bearing", bearing.bearing.toFloat())
            .putString("bearing_source", bearing.source)
            .putString("photo_uid", bearing.photoUid)
            .putInt("accuracy", bearing.accuracyLevel ?: -1)
            .putLong("bearing_ts", bearing.ts ?: 0L)
            .apply()
    }
}
