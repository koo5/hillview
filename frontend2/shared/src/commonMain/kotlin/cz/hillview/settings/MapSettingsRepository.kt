package cz.hillview.settings

import cz.hillview.map.BearingMode
import cz.hillview.map.DEFAULT_TILE_PROVIDER
import kotlinx.coroutines.flow.StateFlow

data class MapSettings(
    val tileProviderKey: String = DEFAULT_TILE_PROVIDER,
    /**
     * How many recent photos the map draws. Bounds match the Tauri filters
     * dialog's maxPhotosInArea (10…1000, default 100).
     */
    val maxPhotos: Int = 100,
    val bearingMode: BearingMode = BearingMode.Walking,
    /** Rotate the map to the sensor heading (the Tauri app's compassEnabled). */
    val compassEnabled: Boolean = false,
    /**
     * Which fusion the shared EnhancedSensorService runs; values are its
     * MODE_* constants (4 = upright rotation vector, its default).
     */
    val sensorMode: Int = 4,
)

const val MIN_MAX_PHOTOS = 10
const val MAX_MAX_PHOTOS = 1000

interface MapSettingsRepository {
    val settings: StateFlow<MapSettings>
    fun update(transform: (MapSettings) -> MapSettings)
}
