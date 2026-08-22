package cz.hillview.settings

import cz.hillview.capture.DEFAULT_JPEG_QUALITY
import cz.hillview.capture.StillCaptureMode
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
     * The geo debug readout (see GeoDebugText): the elected bearing, who
     * wrote it and how long ago, next to the engine's raw heading. Off by
     * default — it is for answering "why is that number not moving?", not
     * for carrying around.
     */
    val showGeoDebug: Boolean = false,
    /**
     * "Do not show again" for the capture pane's bearing-tracking hint —
     * the original's hideBearingTrackingHint, kept because the hint answers
     * a question ("why is the heading not moving?") that only needs
     * answering until the user knows.
     */
    val hideBearingTrackingHint: Boolean = false,
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
    // The eco intensity the Leaf's long-press slider picks: 0 = the
    // preview refreshes only on capture, 0.1..30 = an fps cap (duty-cycled
    // below ECO_DUTY_MAX_FPS), 30 = the untouched default. Applied only
    // while powerSavingPref is on. 15 = the pre-slider eco behaviour.
    val ecoFps: Float = 15f,
    // Per-source toggle overrides (the original's persisted sourceStates):
    // absent = the source's own default (hillview/device on).
    val sourceStates: Map<String, Boolean> = emptyMap(),
    /** CameraOverlay backdrop level 0-5 (Tauri cameraOverlayOpacity). */
    val cameraOverlayOpacity: Int = 3,
    /** Pinned still size as "WxH"; null = auto (Tauri selectedResolution). */
    val captureResolution: String? = null,
    /**
     * What sits between the shutter press and the exposure — see
     * StillCaptureMode. A frontend2 knob (the original has no say in this;
     * its WebView camera does whatever the browser does); persisted beside
     * the resolution it is bound with.
     */
    val stillCaptureMode: StillCaptureMode = StillCaptureMode.DEFAULT,
    /** JPEG quality of the saved stills, 1..100 (CaptureState.jpegQuality). */
    val jpegQuality: Int = DEFAULT_JPEG_QUALITY,
    /**
     * The Main page's activity — "view" or "capture" — persisted so the
     * mode survives restarts, as the Tauri appSettings.activity does.
     */
    val mainActivity: String = "view",
    /** The Main page's split position (photo panel %, Tauri splitPercent). */
    val splitPercent: Float = 50f,
    /**
     * How often the fused provider is asked for a fix, milliseconds. Fed
     * straight to the GeoEngine by BindGeoToActivity — one of the two knobs
     * that decide what tracking costs in battery.
     *
     * It is also the RESOLUTION of everything downstream: a capture's stamp
     * is only as fresh as the last fix, and the refiner interpolates between
     * the two fixes bracketing the shutter, so widening this coarsens both.
     * 1 s is what both apps have always used.
     */
    val gpsIntervalMs: Long = 1_000L,
)

/** The fix cadences the slider offers — 1 s (both apps' default) to 30 s. */
val GPS_INTERVAL_CHOICES_MS: List<Long> =
    listOf(1_000L, 2_000L, 5_000L, 10_000L, 30_000L)

fun formatGpsInterval(ms: Long): String =
    if (ms % 1000L == 0L) "${ms / 1000}s" else "${ms}ms"

const val MIN_MAX_PHOTOS = 10
const val MAX_MAX_PHOTOS = 1000

interface MapSettingsRepository {
    val settings: StateFlow<MapSettings>
    fun update(transform: (MapSettings) -> MapSettings)
}
