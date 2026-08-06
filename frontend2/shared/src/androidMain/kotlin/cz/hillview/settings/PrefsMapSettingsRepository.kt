package cz.hillview.settings

import android.content.Context
import cz.hillview.map.BearingMode
import cz.hillview.map.DEFAULT_TILE_PROVIDER
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class PrefsMapSettingsRepository(context: Context) : MapSettingsRepository {
    private val prefs = context.getSharedPreferences("hillview_map_prefs", Context.MODE_PRIVATE)

    private val _settings = MutableStateFlow(
        MapSettings(
            tileProviderKey = prefs.getString("tile_provider", null) ?: DEFAULT_TILE_PROVIDER,
            maxPhotos = prefs.getInt("max_photos", 100),
            bearingMode = if (prefs.getString("bearing_mode", null) == "car") {
                BearingMode.Car
            } else {
                BearingMode.Walking
            },
            compassEnabled = prefs.getBoolean("compass_enabled", false),
            sensorMode = prefs.getInt("sensor_mode", 4),
        )
    )
    override val settings: StateFlow<MapSettings> = _settings.asStateFlow()

    override fun update(transform: (MapSettings) -> MapSettings) {
        val next = transform(_settings.value)
        prefs.edit()
            .putString("tile_provider", next.tileProviderKey)
            .putInt("max_photos", next.maxPhotos.coerceIn(MIN_MAX_PHOTOS, MAX_MAX_PHOTOS))
            .putString("bearing_mode", if (next.bearingMode == BearingMode.Car) "car" else "walking")
            .putBoolean("compass_enabled", next.compassEnabled)
            .putInt("sensor_mode", next.sensorMode)
            .apply()
        _settings.value = next
    }
}
