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
            hunterModePref = prefs.getBoolean("hunter_mode", false),
            showUnanalyzed = prefs.getBoolean("show_unanalyzed", true),
            powerSavingPref = prefs.getBoolean("power_saving", false),
            cameraOverlayOpacity = prefs.getInt("camera_overlay_opacity", 3),
            captureResolution = prefs.getString("capture_resolution", null),
            mainActivity = prefs.getString("main_activity", null) ?: "view",
            splitPercent = prefs.getFloat("split_percent", 50f),
        )
    )
    override val settings: StateFlow<MapSettings> = _settings.asStateFlow()

    override fun update(transform: (MapSettings) -> MapSettings) {
        val next = transform(_settings.value)
        prefs.edit()
            .putString("tile_provider", next.tileProviderKey)
            .putInt("max_photos", next.maxPhotos.coerceIn(MIN_MAX_PHOTOS, MAX_MAX_PHOTOS))
            .putString("bearing_mode", if (next.bearingMode == BearingMode.Car) "car" else "walking")
            .putBoolean("hunter_mode", next.hunterModePref)
            .putBoolean("show_unanalyzed", next.showUnanalyzed)
            .putBoolean("power_saving", next.powerSavingPref)
            .putInt("camera_overlay_opacity", next.cameraOverlayOpacity.coerceIn(0, 5))
            .putString("capture_resolution", next.captureResolution)
            .putString("main_activity", next.mainActivity)
            .putFloat("split_percent", next.splitPercent.coerceIn(10f, 90f))
            .apply()
        _settings.value = next
    }
}
