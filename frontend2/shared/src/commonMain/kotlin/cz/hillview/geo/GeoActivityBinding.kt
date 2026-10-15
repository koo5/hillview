package cz.hillview.geo

import androidx.compose.runtime.Composable
import cz.hillview.map.BearingMode
import cz.hillview.map.LocationTracking

/**
 * Binds the app's ACTIVITY to what the geo hardware runs — the one place
 * that decides when position and heading are being recorded, and with what.
 *
 * The ACTIVITY drives WHEN (this is the user's mental model, and the code's:
 * `MapSettings.mainActivity` = capture / external / view); the call site
 * supplies WHAT, so a user-facing control — the GPS interval slider, the eco
 * sub-flags — is a value passed through rather than a new mechanism. See
 * `cz.hillview.geo.GeoDefaults` on Android for the starting numbers.
 *
 * Being one call in MainScreen is the point: "why is the GPS awake right
 * now" has a single, readable answer, which a reference count could never
 * give.
 */
@Composable
expect fun BindGeoToActivity(
    /** `MapSettings.mainActivity`: "capture" | "external" | "view". */
    activity: String,
    /** What the map pane needs when the activity asks for nothing more — [mapGeoNeed]. */
    mapNeeds: MapGeoNeed,
    /** Persisted GPS cadence; the slider's value once that exists. */
    gpsIntervalMs: Long,
)

/** What the map pane needs from the geo hardware. */
enum class MapGeoNeed {
    Nothing,
    /** The compass, and a position only for its declination. */
    Compass,
    /** The fix stream. */
    Fixes,
}

/**
 * The map's half of the decision. Follow-me needs fixes; so does the arrow in
 * CAR mode, whose heading IS the GPS course. The walking compass on its own
 * needs only a rough position for declination, which the engine keeps fresh
 * without a stream (user, 2026-10-11: "gps should possibly turn on for compass
 * declination, but that should become some logic that just ensures that the
 * oldest fix is no older than some reasonable value"). It used to run the
 * stream for that, at 2 s.
 */
fun mapGeoNeed(
    locationTracking: LocationTracking,
    bearingWanted: Boolean,
    bearingMode: BearingMode,
): MapGeoNeed = when {
    locationTracking != LocationTracking.Off -> MapGeoNeed.Fixes
    bearingWanted && bearingMode == BearingMode.Car -> MapGeoNeed.Fixes
    bearingWanted -> MapGeoNeed.Compass
    else -> MapGeoNeed.Nothing
}
