package cz.hillview.settings

import android.content.Context
import cz.hillview.capture.DEFAULT_JPEG_QUALITY
import cz.hillview.capture.StillCaptureMode
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
            hideBearingTrackingHint = prefs.getBoolean("hide_bearing_tracking_hint", false),
            showUnanalyzed = prefs.getBoolean("show_unanalyzed", true),
            powerSavingPref = prefs.getBoolean("power_saving", false),
            ecoFps = prefs.getFloat("eco_fps", 15f),
            sourceStates = prefs.getString("source_states", null)
                ?.split(',')
                ?.mapNotNull { entry ->
                    val (id, v) = entry.split('=').takeIf { it.size == 2 }
                        ?: return@mapNotNull null
                    id to (v == "1")
                }
                ?.toMap()
                ?: emptyMap(),
            cameraOverlayOpacity = prefs.getInt("camera_overlay_opacity", 3),
            captureResolution = prefs.getString("capture_resolution", null),
            stillCaptureMode = StillCaptureMode.fromKey(prefs.getString("still_capture_mode", null)),
            jpegQuality = prefs.getInt("jpeg_quality", DEFAULT_JPEG_QUALITY),
            mainActivity = prefs.getString("main_activity", null) ?: "view",
            splitPercent = prefs.getFloat("split_percent", 50f),
            gpsIntervalMs = prefs.getLong("gps_interval_ms", 1_000L),
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
            .putBoolean("hide_bearing_tracking_hint", next.hideBearingTrackingHint)
            .putBoolean("show_unanalyzed", next.showUnanalyzed)
            .putBoolean("power_saving", next.powerSavingPref)
            .putFloat("eco_fps", next.ecoFps.coerceIn(0f, 30f))
            .putString(
                "source_states",
                next.sourceStates.entries
                    .joinToString(",") { "${it.key}=${if (it.value) 1 else 0}" },
            )
            .putInt("camera_overlay_opacity", next.cameraOverlayOpacity.coerceIn(0, 5))
            .putString("capture_resolution", next.captureResolution)
            .putString("still_capture_mode", next.stillCaptureMode.key)
            .putInt("jpeg_quality", next.jpegQuality.coerceIn(1, 100))
            .putLong("gps_interval_ms", next.gpsIntervalMs.coerceIn(250L, 60_000L))
            .putString("main_activity", next.mainActivity)
            .putFloat("split_percent", next.splitPercent.coerceIn(10f, 90f))
            .apply()
        _settings.value = next
    }
}
