package cz.hillview.geo

import androidx.compose.runtime.Composable

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
    /** Follow-me or the compass arrow is on, so the map wants a stream. */
    mapWantsTracking: Boolean,
    /** Persisted GPS cadence; the slider's value once that exists. */
    gpsIntervalMs: Long,
)
