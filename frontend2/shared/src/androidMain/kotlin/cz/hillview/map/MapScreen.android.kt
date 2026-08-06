package cz.hillview.map

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationListener
import android.location.LocationManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
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
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

/**
 * The orientation map, ported control-for-control from the Tauri app —
 * see docs/tauri-map-ui-contract.md, which is the spec this follows.
 */
@Composable
actual fun MapScreen(
    onBack: () -> Unit,
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
    stateStore: MapStateStore,
) {
    val context = LocalContext.current
    val mapSettings by settings.settings.collectAsState()
    val markers by markerSource.markers.collectAsState()

    // Restored, so the bearing survives backgrounding and restarts — the
    // Appium suite asserts it is unchanged after the app comes back.
    val state = remember {
        stateStore.load()
            ?.let { (spatial, bearing) -> MapStateHolder(spatial, bearing) }
            ?: MapStateHolder()
    }
    val spatial by state.spatial.collectAsState()
    val bearing by state.bearing.collectAsState()

    // Hunter mode: persisted preference, overridable per session.
    var hunterOverride by remember { mutableStateOf<Boolean?>(null) }
    val hunterMode = hunterOverride ?: mapSettings.hunterModePref

    // Session-only, exactly as in the Svelte app.
    var trackingWanted by remember { mutableStateOf(false) }
    var trackingPhase by remember { mutableStateOf(TrackingPhase.Inactive) }
    var locationTracking by remember { mutableStateOf(LocationTracking.Off) }
    var locationFlash by remember { mutableStateOf(false) }
    var overrideFilters by remember { mutableStateOf(false) }
    var showFilters by remember { mutableStateOf(false) }
    var showProviders by remember { mutableStateOf(false) }
    var deviceSourceEnabled by remember { mutableStateOf(true) }
    var arrowTipPx by remember { mutableStateOf(120f) }

    val controller = remember { MapSensorController(context.applicationContext) }
    DisposableEffect(controller) { onDispose { controller.release() } }

    // Bearing tracking: walking runs the compass, car runs GPS orientation.
    // A failed start reverts the user's intent, like the original.
    LaunchedEffect(trackingWanted, mapSettings.bearingMode) {
        if (!trackingWanted) {
            controller.stopBearing()
            trackingPhase = TrackingPhase.Inactive
            return@LaunchedEffect
        }
        trackingPhase = TrackingPhase.Starting
        val started = controller.startBearing(mapSettings.bearingMode) { heading, accuracy ->
            trackingPhase = TrackingPhase.Active
            // Only the compass drives the view bearing directly, and only
            // past a 1° dead-band.
            if (mapSettings.bearingMode == BearingMode.Walking &&
                absBearingDiff(heading.toDouble(), state.bearing.value.bearing) > 1.0
            ) {
                state.updateBearing(
                    bearing = heading.toDouble(),
                    source = "android-compass-true",
                    accuracyLevel = accuracy,
                    now = System.currentTimeMillis(),
                )
            }
        }
        if (!started) {
            trackingPhase = TrackingPhase.Error
            trackingWanted = false
            trackingPhase = TrackingPhase.Inactive
        }
    }

    // GPS: runs in ACTIVE and BACKGROUND, only ACTIVE moves the map.
    LaunchedEffect(locationTracking) {
        controller.setLocationEnabled(locationTracking != LocationTracking.Off) { lat, lon ->
            locationFlash = true
            if (locationTracking == LocationTracking.Active) {
                state.updateSpatial(
                    latitude = lat, longitude = lon,
                    source = "gps", now = System.currentTimeMillis(),
                )
            }
        }
    }
    LaunchedEffect(locationFlash) {
        if (locationFlash) { delay(100); locationFlash = false }
    }

    LaunchedEffect(mapSettings.maxPhotos) {
        while (true) {
            markerSource.refresh()
            delay(5_000)
        }
    }

    LaunchedEffect(spatial, bearing) {
        stateStore.save(spatial, bearing)
    }

    val markerOverlay = remember { PhotoMarkerOverlay() }
    val rangeOverlay = remember { RangeCircleOverlay() }
    val mapView = rememberMapView()
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
                if (rangeOverlay !in view.overlays) view.overlays.add(rangeOverlay)
                if (markerOverlay !in view.overlays) view.overlays.add(markerOverlay)

                // The ring is screen-constant: 70 CSS pixels in the web app,
                // so 70dp here. `range` is what that radius happens to mean
                // on the ground at this zoom — used for in-range/greying,
                // never for drawing.
                val centre = GeoPoint(spatial.latitude, spatial.longitude)
                val density = view.context.resources.displayMetrics.density
                val ringPx = 70f * density
                val rangeMeters = view.projection.let { p ->
                    val a = p.toPixels(centre, null)
                    val b = p.fromPixels(a.x + ringPx.toInt(), a.y)
                    centre.distanceToAsDouble(b)
                }.takeIf { it > 0 } ?: spatial.range
                rangeOverlay.centre = centre
                rangeOverlay.radiusPx = ringPx
                // Tip at 1.3x the ring, as in the original — just outside it.
                arrowTipPx = ringPx * 1.3f

                markerOverlay.viewBearing = bearing.bearing
                // Greying rule from the contract: outside hunter mode, when
                // featured photos exist, non-featured ones INSIDE the range
                // circle are washed out (outside it they are not).
                val visible = markers.filter { deviceSourceEnabled || it.source != "device" }
                val anyFeatured = visible.any { it.featured }
                markerOverlay.markers = visible.map { marker ->
                    val greyed = !hunterMode && anyFeatured && !marker.featured &&
                        centre.distanceToAsDouble(
                            GeoPoint(marker.latitude, marker.longitude),
                        ) <= rangeMeters
                    if (greyed == marker.greyed) marker else marker.copy(greyed = greyed)
                }

                if (applied.zoom != spatial.zoom) {
                    view.controller.setZoom(spatial.zoom)
                    applied.zoom = spatial.zoom
                }
                if (applied.latitude != spatial.latitude || applied.longitude != spatial.longitude) {
                    view.controller.setCenter(centre)
                    applied.latitude = spatial.latitude
                    applied.longitude = spatial.longitude
                }
                if (kotlin.math.abs(applied.bearing - bearing.bearing) > 1.0) {
                    view.mapOrientation = -bearing.bearing.toFloat()
                    applied.bearing = bearing.bearing
                }
                view.invalidate()
            },
        )

        BearingArrow(
            bearingDeg = bearing.bearing,
            // Car mode makes the whole ring grabbable, and only while GPS
            // orientation is actually running.
            fullCircleHitArea = mapSettings.bearingMode == BearingMode.Car && trackingWanted,
            tipRadiusPx = arrowTipPx,
            onDragStart = {
                // Dragging the arrow stops the compass — but not GPS
                // orientation, whose drag means "adjust the mount".
                if (mapSettings.bearingMode == BearingMode.Walking && trackingWanted) {
                    trackingWanted = false
                }
            },
            onBearing = { value ->
                state.updateBearing(value, source = "arrow_drag", now = System.currentTimeMillis())
            },
            onBearingDelta = { delta ->
                controller.adjustMountOffset(delta)
                state.updateBearingByDiff(delta, source = "gps-kalman", now = System.currentTimeMillis())
            },
        )

        MapOverlayUi(
            onBack = onBack,
            settings = mapSettings,
            hunterMode = hunterMode,
            sources = listOf(
                MapSourceUi(id = "device", name = "Device", enabled = deviceSourceEnabled),
            ),
            activeFilterCount = 0,
            overrideFilters = overrideFilters,
            locationTracking = locationTracking,
            locationFlash = locationFlash,
            locationLoading = false,
            powerSavingActive = false,
            trackingWanted = trackingWanted,
            trackingPhase = trackingPhase,
            compassUnavailable = mapSettings.bearingMode == BearingMode.Walking &&
                !controller.compassAvailable(),
            markerCount = markers.size,
            onToggleHunterMode = {
                hunterOverride = null
                settings.update { it.copy(hunterModePref = !hunterMode) }
            },
            onToggleSource = { deviceSourceEnabled = !deviceSourceEnabled },
            onOpenFilters = { showFilters = true },
            onToggleOverrideFilters = { overrideFilters = !overrideFilters },
            onOpenTileProviders = { showProviders = true },
            onToggleLocation = {
                locationTracking = when (locationTracking) {
                    // ACTIVE or BACKGROUND both turn fully off.
                    LocationTracking.Active, LocationTracking.Background -> LocationTracking.Off
                    LocationTracking.Off -> LocationTracking.Active
                }
            },
            onToggleTracking = { trackingWanted = !trackingWanted },
            onSelectBearingMode = { mode ->
                // Picking a mode stops the old tracker and starts the new
                // one — enabling tracking is a deliberate side effect of the
                // choice, not something the user has to do afterwards.
                trackingWanted = false
                settings.update { it.copy(bearingMode = mode) }
                trackingWanted = true
            },
            onZoom = { delta ->
                state.updateSpatial(
                    zoom = (spatial.zoom + delta).coerceIn(3.0, 22.0),
                    now = System.currentTimeMillis(),
                )
            },
        )

        if (showFilters) {
            FiltersDialog(
                settings = mapSettings,
                onDismiss = { showFilters = false },
                onSettingsChange = { transform -> settings.update(transform) },
            )
        }
        if (showProviders) {
            TileProviderDialog(
                currentKey = mapSettings.tileProviderKey,
                onPick = { key -> settings.update { it.copy(tileProviderKey = key) } },
                onDismiss = { showProviders = false },
            )
        }
    }

    // Panning demotes ACTIVE to BACKGROUND rather than stopping GPS.
    DisposableEffect(mapView, locationTracking) {
        val listener = object : org.osmdroid.events.MapListener {
            override fun onScroll(event: org.osmdroid.events.ScrollEvent?): Boolean {
                if (locationTracking == LocationTracking.Active) {
                    locationTracking = LocationTracking.Background
                }
                return false
            }

            override fun onZoom(event: org.osmdroid.events.ZoomEvent?): Boolean = false
        }
        mapView.addMapListener(listener)
        onDispose { mapView.removeMapListener(listener) }
    }
}

@Composable
private fun rememberMapView(): MapView {
    val context = LocalContext.current
    val mapView = remember {
        initOsmdroid(context.applicationContext)
        MapView(context).apply {
            setMultiTouchControls(true)
            isTilesScaledToDpi = true
        }
    }
    DisposableEffect(mapView) { onDispose { mapView.onDetach() } }
    return mapView
}

private class AppliedCamera {
    var providerKey: String? = null
    var latitude = Double.NaN
    var longitude = Double.NaN
    var zoom = Double.NaN
    var bearing = Double.NaN
}

/**
 * Sensors and GPS for the map, over the shared-kt stack. Bearing tracking
 * and location tracking are separate concerns here exactly as they are in
 * the Svelte app.
 */
private class MapSensorController(private val context: Context) {
    private val locationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private val geoTracking by lazy { GeoTrackingManager(context) }

    private var sensorService: EnhancedSensorService? = null
    private var locationListener: LocationListener? = null

    fun compassAvailable(): Boolean =
        (context.getSystemService(Context.SENSOR_SERVICE) as android.hardware.SensorManager)
            .getDefaultSensor(android.hardware.Sensor.TYPE_ROTATION_VECTOR) != null

    /** @return false when the sensor could not be started (reverts intent). */
    fun startBearing(mode: BearingMode, onHeading: (Float, Int?) -> Unit): Boolean {
        stopBearing()
        if (mode == BearingMode.Walking && !compassAvailable()) return false
        return try {
            sensorService = EnhancedSensorService(context) { data ->
                onHeading(data.trueHeading, data.accuracyLevel)
            }.also { it.startSensor() }
            true
        } catch (e: Exception) {
            sensorService = null
            false
        }
    }

    fun stopBearing() {
        sensorService?.stopSensor()
        sensorService = null
    }

    @SuppressLint("MissingPermission")
    fun setLocationEnabled(enabled: Boolean, onFix: (Double, Double) -> Unit) {
        if (!enabled) {
            locationListener?.let {
                try {
                    locationManager.removeUpdates(it)
                } catch (e: Exception) {
                    // already gone
                }
            }
            locationListener = null
            return
        }
        if (locationListener != null || !hasLocationPermission()) return
        val listener = LocationListener { location ->
            sensorService?.updateLocation(location.latitude, location.longitude)
            onFix(location.latitude, location.longitude)
        }
        locationListener = listener
        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, 1_000L, 0f, listener,
            )
            locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let {
                onFix(it.latitude, it.longitude)
            }
        } catch (e: Exception) {
            locationListener = null
        }
    }

    /** Car mode: the drag moves the camera mount, not the heading. */
    fun adjustMountOffset(deltaDeg: Double) {
        geoTracking.setMountOffset(geoTracking.getMountOffset() + deltaDeg)
    }

    fun release() {
        stopBearing()
        setLocationEnabled(false) { _, _ -> }
    }

    private fun hasLocationPermission() =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
}
