package cz.hillview.settings

import cz.hillview.map.BearingMode
import cz.hillview.map.DEFAULT_TILE_PROVIDER
import kotlinx.coroutines.flow.StateFlow

/**
 * Only what the Tauri app persists (see docs/tauri-map-ui-contract.md).
 * Deliberately absent: compass/GPS-orientation enablement, the sensor mode
 * and the car mount offset — every session there starts with tracking off,
 * and copying that is the point.
 */
data class MapSettings(
    val tileProviderKey: String = DEFAULT_TILE_PROVIDER,
    /** CullingGrid limit; the Tauri filters modal bounds it to 10…1000. */
    val maxPhotos: Int = 100,
    val bearingMode: BearingMode = BearingMode.Walking,
    /** The persisted half of hunter mode; the override is session-only. */
    val hunterModePref: Boolean = false,
    /**
     * "Show unanalyzed photos": default on, and only *meaningful* once some
     * analysis filter is active — unchecked it greys every photo the
     * analysis has not passed, which locally is all of them. The modal
     * disables it until a filter is active, per the contract.
     */
    val showUnanalyzed: Boolean = true,
    /**
     * The eco toggle (the Leaf on the capture screen). Persisted like the
     * Tauri `powerSaving` localStorage flag; its *effects* apply only while
     * capturing — leaving capture restores normal behaviour with the
     * toggle remembered.
     */
    val powerSavingPref: Boolean = false,
    /** CameraOverlay backdrop level 0-5 (Tauri cameraOverlayOpacity). */
    val cameraOverlayOpacity: Int = 3,
    /** Pinned still size as "WxH"; null = auto (Tauri selectedResolution). */
    val captureResolution: String? = null,
    /**
     * The Main page's activity — "view" or "capture" — persisted so the
     * mode survives restarts, as the Tauri appSettings.activity does.
     */
    val mainActivity: String = "view",
    /** The Main page's split position (photo panel %, Tauri splitPercent). */
    val splitPercent: Float = 50f,
)

const val MIN_MAX_PHOTOS = 10
const val MAX_MAX_PHOTOS = 1000

interface MapSettingsRepository {
    val settings: StateFlow<MapSettings>
    fun update(transform: (MapSettings) -> MapSettings)
}
