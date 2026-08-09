package cz.hillview.geo

import androidx.compose.runtime.Composable

/** Desktop has no geo hardware to drive. */
@Composable
actual fun BindGeoToActivity(
    activity: String,
    mapWantsTracking: Boolean,
    gpsIntervalMs: Long,
) {
}
