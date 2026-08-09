package cz.hillview.geo

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext

@Composable
actual fun BindGeoToActivity(
    activity: String,
    mapWantsTracking: Boolean,
    gpsIntervalMs: Long,
) {
    val context = LocalContext.current.applicationContext
    LaunchedEffect(activity, mapWantsTracking, gpsIntervalMs) {
        val engine = GeoEngine.get(context)
        engine.configure(
            when {
                // The external-camera activity runs its own foreground
                // service, which configures the engine itself — it must keep
                // running while this composition is backgrounded, so the
                // activity binding must not fight it.
                activity == "external" -> return@LaunchedEffect
                activity == "capture" -> captureGeoConfig(gpsIntervalMs)
                mapWantsTracking -> mapOnlyGeoConfig()
                else -> GeoConfig.Off
            },
        )
    }
}
