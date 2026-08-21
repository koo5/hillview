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
                // service, which claims the engine itself so it can keep
                // running while this composition is backgrounded. The
                // activity claims the SAME thing rather than standing aside:
                // two identical claims merge to one config, so neither the
                // handover in nor the handover out has a gap — and whichever
                // of the two goes away first, the other still holds it.
                activity == "external" -> externalCameraConfig(gpsIntervalMs)
                activity == "capture" -> captureGeoConfig(gpsIntervalMs)
                mapWantsTracking -> mapOnlyGeoConfig()
                else -> GeoConfig.Off
            },
        )
    }
}
