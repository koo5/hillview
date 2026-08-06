package cz.hillview.map

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.location.LocationListener
import android.location.LocationManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import cz.hillview.plugin.EnhancedSensorService
import cz.hillview.plugin.GeoTrackingManager
import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.delay
import org.koin.compose.koinInject
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

/**
 * The orientation map: where you are, which way you're pointed, and the
 * photos already taken around you.
 *
 * The heading comes from the shared-kt EnhancedSensorService — the same
 * engine the capture screen uses, so the arrow and the EXIF agree. In car
 * mode the drag adjusts GeoTrackingManager's mount offset instead of the
 * heading itself, exactly like the Tauri app.
 */
@Composable
actual fun MapScreen(
    onBack: () -> Unit,
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
) {
    val context = LocalContext.current
    val mapSettings by settings.settings.collectAsState()
    val markers by markerSource.markers.collectAsState()

    var camera by remember { mutableStateOf(MapCamera()) }
    var sensorHeading by remember { mutableStateOf<Float?>(null) }
    var hasFix by remember { mutableStateOf(false) }

    val controller = remember { MapSensorController(context.applicationContext) }
    DisposableEffect(controller) { onDispose { controller.release() } }

    // Sensors run only while this screen is up (battery discipline, same as
    // the capture screen).
    LaunchedEffect(mapSettings.compassEnabled, mapSettings.sensorMode) {
        controller.apply(
            enabled = mapSettings.compassEnabled,
            mode = mapSettings.sensorMode,
            onHeading = { sensorHeading = it },
            onLocation = { lat, lon, fix ->
                hasFix = fix
                camera = camera.copy(latitude = lat, longitude = lon)
            },
        )
    }

    // While the compass drives the view, the map turns with the heading.
    LaunchedEffect(sensorHeading, mapSettings.compassEnabled, mapSettings.bearingMode) {
        val heading = sensorHeading ?: return@LaunchedEffect
        if (mapSettings.compassEnabled && mapSettings.bearingMode == BearingMode.Walking) {
            camera = camera.copy(bearingDeg = heading.toDouble())
        }
    }

    LaunchedEffect(mapSettings.maxPhotos) {
        while (true) {
            markerSource.refresh()
            delay(5_000)
        }
    }

    val markerOverlay = remember { PhotoMarkerOverlay() }
    val mapView = rememberMapView()
    // What the MapView has already been told, so update() can skip no-ops.
    val applied = remember { AppliedCamera() }

    Box(Modifier.fillMaxSize()) {
        AndroidView(
            factory = { mapView },
            modifier = Modifier.fillMaxSize(),
            update = { view ->
                if (applied.providerKey != mapSettings.tileProviderKey) {
                    view.applyProvider(tileProvider(mapSettings.tileProviderKey))
                    applied.providerKey = mapSettings.tileProviderKey
                }
                if (markerOverlay !in view.overlays) view.overlays.add(markerOverlay)
                markerOverlay.markers = markers

                // Only push what actually changed. Re-issuing setCenter/setZoom
                // on every recomposition (the compass ticks at ~4 Hz) restarts
                // the tile requests each time and the map never finishes
                // loading — it renders as bare grid.
                if (applied.zoom != camera.zoom) {
                    view.controller.setZoom(camera.zoom)
                    applied.zoom = camera.zoom
                }
                if (applied.latitude != camera.latitude || applied.longitude != camera.longitude) {
                    view.controller.setCenter(GeoPoint(camera.latitude, camera.longitude))
                    applied.latitude = camera.latitude
                    applied.longitude = camera.longitude
                }
                // Rotation is cheap to apply but forces a full redraw, so move
                // it only when the heading meaningfully changed.
                if (kotlin.math.abs(applied.bearing - camera.bearingDeg) > 1.0) {
                    view.mapOrientation = -camera.bearingDeg.toFloat()
                    applied.bearing = camera.bearingDeg
                }
                view.invalidate()
            },
        )

        MapOverlayUi(
            onBack = onBack,
            camera = camera,
            settings = mapSettings,
            markerCount = markers.size,
            hasFix = hasFix,
            sensorHeading = sensorHeading,
            onBearingDrag = { bearing ->
                if (mapSettings.bearingMode == BearingMode.Car) {
                    // Car mode moves the camera mount, not the heading.
                    controller.adjustMountOffset(bearing - camera.bearingDeg)
                }
                camera = camera.copy(bearingDeg = bearing)
            },
            onCompassDisabledByDrag = {
                if (mapSettings.compassEnabled) {
                    settings.update { it.copy(compassEnabled = false) }
                }
            },
            onSettingsChange = { transform -> settings.update(transform) },
            onZoom = { delta -> camera = camera.copy(zoom = (camera.zoom + delta).coerceIn(3.0, 22.0)) },
        )
    }
}

@Composable
private fun rememberMapView(): MapView {
    val context = LocalContext.current
    val mapView = remember {
        initOsmdroid(context.applicationContext)
        MapView(context).apply {
            setMultiTouchControls(true)
            // The bearing arrow owns rotation; osmdroid's own rotation gesture
            // would fight it.
            isTilesScaledToDpi = true
        }
    }
    DisposableEffect(mapView) {
        onDispose { mapView.onDetach() }
    }
    return mapView
}

/** Mutable holder — deliberately not state; nothing recomposes on it. */
private class AppliedCamera {
    var providerKey: String? = null
    var latitude = Double.NaN
    var longitude = Double.NaN
    var zoom = Double.NaN
    var bearing = Double.NaN
}

/**
 * Heading + location for the map, over the shared sensor stack. Keeping it
 * out of the composable means the listeners have a lifetime we control.
 */
private class MapSensorController(private val context: Context) {
    private val locationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private val geoTracking by lazy { GeoTrackingManager(context) }

    private var sensorService: EnhancedSensorService? = null
    private var locationListener: LocationListener? = null
    private var runningMode: Int? = null

    @SuppressLint("MissingPermission")
    fun apply(
        enabled: Boolean,
        mode: Int,
        onHeading: (Float?) -> Unit,
        onLocation: (Double, Double, Boolean) -> Unit,
    ) {
        if (locationListener == null && hasLocationPermission()) {
            val listener = LocationListener { location ->
                sensorService?.updateLocation(location.latitude, location.longitude)
                onLocation(location.latitude, location.longitude, true)
            }
            locationListener = listener
            try {
                locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER, 1_000L, 0f, listener,
                )
                locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let {
                    onLocation(it.latitude, it.longitude, true)
                }
            } catch (e: Exception) {
                locationListener = null
            }
        }

        if (!enabled) {
            sensorService?.stopSensor()
            sensorService = null
            runningMode = null
            onHeading(null)
            return
        }
        if (sensorService != null && runningMode == mode) return

        sensorService?.stopSensor()
        sensorService = EnhancedSensorService(context) { data ->
            onHeading(data.trueHeading)
        }.also {
            it.startSensor(mode)
            runningMode = mode
        }
    }

    fun adjustMountOffset(deltaDeg: Double) {
        geoTracking.setMountOffset(geoTracking.getMountOffset() + deltaDeg)
    }

    fun release() {
        sensorService?.stopSensor()
        sensorService = null
        locationListener?.let {
            try {
                locationManager.removeUpdates(it)
            } catch (e: Exception) {
                // already gone
            }
        }
        locationListener = null
    }

    private fun hasLocationPermission() =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
}
