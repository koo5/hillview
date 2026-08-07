package cz.hillview.map

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationListener
import android.location.LocationManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import cz.hillview.plugin.EnhancedSensorService
import cz.hillview.plugin.GeoTrackingManager
import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.delay
import kotlin.math.roundToInt
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
    session: MapSession,
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

    // Session-only, exactly as in the Svelte app — but held in MapSession
    // rather than the composition, because the map is its own destination
    // here and a trip through capture would otherwise reset it. The effects
    // below keep the two in step in both directions: what the user does on
    // this screen is written back, and what happened while the screen was
    // away (capture arming a clean ACTIVE) is adopted.
    var trackingWanted by remember { mutableStateOf(session.bearingTrackingWanted.value) }
    var trackingPhase by remember { mutableStateOf(TrackingPhase.Inactive) }
    var locationTracking by remember { mutableStateOf(session.locationTracking.value) }
    var locationFlash by remember { mutableStateOf(false) }
    // A pan happened and no manual position is claimed: exploration is
    // free, and this offers the two exits — claim this position, or snap
    // back to the fix. No timeout: reading a map takes as long as it
    // takes.
    var positionPrompt by remember { mutableStateOf(false) }
    val manualClaimed by session.manualPositionClaimed.collectAsState()
    var overrideFilters by remember { mutableStateOf(false) }
    var showFilters by remember { mutableStateOf(false) }
    var showProviders by remember { mutableStateOf(false) }
    var deviceSourceEnabled by remember { mutableStateOf(true) }
    var arrowTipPx by remember { mutableStateOf(120f) }
    // The front photo: what the gallery would show and the marker drawn as
    // selected. Recomputed from bearing + range, or set by tapping.
    var selectedPhotoId by remember { mutableStateOf<String?>(null) }
    // Published by the marker overlay after each draw that moved anything.
    var markerPositions by remember {
        mutableStateOf<List<Pair<String, Pair<Float, Float>>>>(emptyList())
    }
    val density = LocalDensity.current

    val sessionLocation by session.locationTracking.collectAsState()
    val sessionBearingWanted by session.bearingTrackingWanted.collectAsState()
    LaunchedEffect(sessionLocation) { locationTracking = sessionLocation }
    LaunchedEffect(sessionBearingWanted) { trackingWanted = sessionBearingWanted }
    LaunchedEffect(locationTracking) { session.setLocationTracking(locationTracking) }
    LaunchedEffect(trackingWanted) { session.setBearingTrackingWanted(trackingWanted) }

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
    // The location button is the stronger control: using it while the
    // prompt is up answers it.
    LaunchedEffect(locationTracking) {
        if (locationTracking != LocationTracking.Background) positionPrompt = false
    }

    LaunchedEffect(spatial, bearing) {
        stateStore.save(spatial, bearing)
    }

    // Pin the selection so the photo limit can never drop it out from under
    // the user.
    LaunchedEffect(selectedPhotoId) {
        markerSource.pinnedId = selectedPhotoId
    }

    val markerOverlay = remember { PhotoMarkerOverlay() }
    markerOverlay.onDrawn = { markerPositions = it }
    val rangeOverlay = remember { RangeCircleOverlay() }
    val arrowOverlay = remember { BearingArrowOverlay() }
    // Arrow drag: walking sets the bearing outright, car adjusts the mount
    // offset by the angle travelled.
    arrowOverlay.onDragStart = {
        if (mapSettings.bearingMode == BearingMode.Walking && trackingWanted) {
            trackingWanted = false
        }
    }
    arrowOverlay.onBearing = { value ->
        state.updateBearing(value, source = "arrow_drag", now = System.currentTimeMillis())
    }
    arrowOverlay.onBearingDelta = { delta ->
        controller.adjustMountOffset(delta)
        state.updateBearingByDiff(delta, source = "gps-kalman", now = System.currentTimeMillis())
    }
    val mapView = rememberMapView()
    val applied = remember { AppliedCamera() }

    // The marker poll: tell the sources where the map is looking (the
    // backend source queries by viewport; pre-layout the view has no real
    // bounding box, so wait for a size), then refresh. The api source
    // dedupes identical requests internally, so the 5 s cadence stays a
    // local-DB cost between real moves.
    LaunchedEffect(mapSettings.maxPhotos) {
        while (true) {
            if (mapView.width > 0) {
                val box = mapView.boundingBox
                markerSource.setViewport(
                    MapViewport(
                        topLeftLat = box.latNorth,
                        topLeftLon = box.lonWest,
                        bottomRightLat = box.latSouth,
                        bottomRightLon = box.lonEast,
                    ),
                )
            }
            markerSource.refresh()
            delay(5_000)
        }
    }
    val rotationOverlay = remember(mapView) {
        RotationSyncOverlay(mapView) { orientation ->
            applied.orientation = orientation
            state.updateSpatial(
                orientation = orientation,
                source = "map",
                now = System.currentTimeMillis(),
            )
        }
    }

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
                // Late, so it draws on top — and so its touch handler gets
                // refusal before the map pans.
                if (arrowOverlay !in view.overlays) view.overlays.add(arrowOverlay)
                // Truly last: osmdroid offers touches to overlays in reverse,
                // so this sees every pointer first. It never consumes them,
                // it only watches for the second finger.
                if (rotationOverlay !in view.overlays) view.overlays.add(rotationOverlay)

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
                arrowOverlay.bearingDeg = bearing.bearing
                arrowOverlay.tipRadiusPx = arrowTipPx
                arrowOverlay.fullCircleHitArea =
                    mapSettings.bearingMode == BearingMode.Car && trackingWanted

                markerOverlay.viewBearing = bearing.bearing
                markerOverlay.onPhotoTapped = { photo ->
                    // Turning the view to the photo IS the selection — the
                    // bearing carries the photo id, exactly as the original
                    // does via updateBearingWithPhoto.
                    photo.bearingDeg?.let { photoBearing ->
                        state.updateBearing(
                            bearing = photoBearing,
                            source = "marker_click",
                            photoUid = photo.id,
                            now = System.currentTimeMillis(),
                        )
                    }
                    selectedPhotoId = photo.id
                    // Tapping a greyed-out photo un-greys the set, like the
                    // original's overrideFilters flip.
                    if (!hunterMode) hunterOverride = true
                }
                // Greying rule from the contract: outside hunter mode, when
                // featured photos exist, non-featured ones INSIDE the range
                // circle are washed out (outside it they are not).
                val visible = markers.filter { deviceSourceEnabled || it.source != "device" }
                val anyFeatured = visible.any { it.featured }

                // The front photo follows the view unless the user picked
                // one; a bearing whose source is a tap keeps that choice.
                val inRange = { m: PhotoMarker ->
                    centre.distanceToAsDouble(GeoPoint(m.latitude, m.longitude)) <= rangeMeters
                }
                selectedPhotoId = if (bearing.photoUid != null) {
                    bearing.photoUid
                } else {
                    frontPhoto(visible, bearing.bearing, { it.id }, { it.bearingDeg }, inRange)?.id
                }
                markerOverlay.selectedId = selectedPhotoId
                markerOverlay.markers = visible.map { marker ->
                    // Two wash-out reasons compose: the backend's analysis
                    // filter verdict (unless overridden), and the
                    // featured-range rule.
                    val greyed = (marker.filteredOut && !overrideFilters) ||
                        (
                            !hunterMode && anyFeatured && !marker.featured &&
                                centre.distanceToAsDouble(
                                    GeoPoint(marker.latitude, marker.longitude),
                                ) <= rangeMeters
                            )
                    if (greyed == marker.greyed) marker else marker.copy(greyed = greyed)
                }

                if (applied.zoom != spatial.zoom) {
                    applied.pushing = true
                    view.controller.setZoom(spatial.zoom)
                    applied.pushing = false
                    applied.zoom = spatial.zoom
                    applied.echoZoom = view.zoomLevelDouble
                }
                if (applied.latitude != spatial.latitude || applied.longitude != spatial.longitude) {
                    applied.pushing = true
                    view.controller.setCenter(centre)
                    applied.pushing = false
                    applied.latitude = spatial.latitude
                    applied.longitude = spatial.longitude
                    applied.echoLatitude = view.mapCenter.latitude
                    applied.echoLongitude = view.mapCenter.longitude
                }
                // The map is north-up unless the user turns it: the bearing
                // is shown by the arrow, exactly as in the original, where
                // Leaflet never rotates. (An earlier version drove
                // mapOrientation from the bearing, which would have spun the
                // map under a drag and moved the arrow at twice the finger.)
                if (applied.orientation != spatial.orientation) {
                    applied.pushing = true
                    view.mapOrientation = spatial.orientation.toFloat()
                    applied.pushing = false
                    applied.orientation = spatial.orientation
                    applied.echoOrientation = view.mapOrientation.toDouble()
                }
                // Echoes read back from an unlaid view (width 0, no real
                // projection) are garbage; they only start meaning something
                // once the map has a size. If the first-layout settle event
                // already validated them (see isOurOwnMove), this is a no-op.
                if (!applied.echoValid && view.width > 0) {
                    applied.echoLatitude = view.mapCenter.latitude
                    applied.echoLongitude = view.mapCenter.longitude
                    applied.echoZoom = view.zoomLevelDouble
                    applied.echoOrientation = view.mapOrientation.toDouble()
                    applied.echoValid = true
                }
                view.invalidate()
            },
        )

        // The arrow itself lives in the map's overlay layer (see
        // BearingArrowOverlay); this node only publishes its value so
        // accessibility services and UI tests can read it without covering
        // the map.
        Box(
            Modifier
                .testTag("map-bearing-arrow")
                .semantics {
                    progressBarRangeInfo = ProgressBarRangeInfo(
                        current = bearing.bearing.toFloat(),
                        range = 0f..360f,
                    )
                    contentDescription = "Bearing ${bearing.bearing.toInt()} degrees"
                },
        )

        // Markers are drawn on a canvas, so nothing in the tree stands for a
        // photo and neither a test nor a screen reader can name one. These
        // carry that identity — the same `photo-marker-<id>` the Appium suite
        // looks for — and sit where the marker actually is, which is what
        // makes them worth having: stacked at one point they would be a
        // single occluded node, and useless to point at.
        //
        // They take no touches, so the map keeps every gesture.
        val byId = markers.associateBy { it.id }
        markerPositions.forEach { (id, at) ->
            val marker = byId[id] ?: return@forEach
            val half = with(density) { 24.dp.toPx() / 2f }
            Box(
                Modifier
                    .offset {
                        IntOffset(
                            (at.first - half).roundToInt(),
                            (at.second - half).roundToInt(),
                        )
                    }
                    .size(24.dp)
                    .testTag("photo-marker-$id")
                    .semantics {
                        stateDescription = if (id == selectedPhotoId) {
                            "selected"
                        } else {
                            "not selected"
                        }
                        contentDescription = marker.bearingDeg
                            ?.let { "Photo facing ${it.toInt()} degrees" }
                            ?: "Photo with no bearing"
                    },
            )
        }

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
            // The badge shows the armed eco preference: with separate
            // screens the Tauri "active while capturing" moment can never
            // coincide with the map being visible, so armed is the honest
            // rendering of the same fact.
            powerSavingActive = mapSettings.powerSavingPref,
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
            positionPrompt = positionPrompt && !manualClaimed,
            onClaimManualPosition = {
                positionPrompt = false
                session.claimManualPosition()
            },
            onRevertToGps = {
                positionPrompt = false
                locationTracking = LocationTracking.Active
            },
            mapOrientation = spatial.orientation,
            onResetNorth = {
                state.updateSpatial(
                    orientation = 0.0,
                    source = "map",
                    now = System.currentTimeMillis(),
                )
            },
        )

        if (showFilters) {
            FiltersDialog(
                settings = mapSettings,
                // No analysis filters exist against the local marker source
                // yet, so nothing can activate the trailing controls — but
                // their gating is real and tested, ready for the backend
                // query.
                activeFilterCount = 0,
                onDismiss = { showFilters = false },
                onSettingsChange = { transform -> settings.update(transform) },
                onClearFilters = { settings.update { it.copy(showUnanalyzed = true) } },
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

    // The upward half of the loop: what the user does to the map becomes
    // state. Without this the store never learns about a pan, and the next
    // state-driven update would yank the view back.
    DisposableEffect(mapView, locationTracking) {
        // osmdroid's MapListener cannot tell a finger from a setCenter —
        // the exact Leaflet failing that forced the original's ts/source
        // machinery. The AppliedCamera is the disambiguator: our own
        // pushes are recorded there *before* the event arrives, so an
        // event that matches it is our echo, and only a mismatch is the
        // user. Without this, the first GPS follow would demote ACTIVE to
        // BACKGROUND and follow-me would undo itself.
        fun isOurOwnMove(): Boolean {
            if (applied.pushing) return true
            if (!applied.echoValid) {
                // The first-layout settle: our camera pushes landed on a view
                // with no size, osmdroid held them (setExpectedCenter) and
                // applies them here, at the first real layout — firing this
                // event from inside the layout pass, synchronously, before
                // any finger could possibly have touched the map. Without
                // this branch that settle mismatched the pre-layout echo
                // garbage and demoted ACTIVE on merely (re)opening the map —
                // i.e. every return from capture.
                applied.echoLatitude = mapView.mapCenter.latitude
                applied.echoLongitude = mapView.mapCenter.longitude
                applied.echoZoom = mapView.zoomLevelDouble
                applied.echoOrientation = mapView.mapOrientation.toDouble()
                applied.echoValid = true
                return true
            }
            val centre = mapView.mapCenter
            return kotlin.math.abs(centre.latitude - applied.echoLatitude) < 1e-9 &&
                kotlin.math.abs(centre.longitude - applied.echoLongitude) < 1e-9 &&
                kotlin.math.abs(mapView.zoomLevelDouble - applied.echoZoom) < 1e-9 &&
                kotlin.math.abs(
                    mapView.mapOrientation.toDouble() - applied.echoOrientation,
                ) < 1e-6
        }

        fun syncFromMap() {
            val centre = mapView.mapCenter
            // Record where the map now is, so the downward path sees no
            // difference and does not re-issue setCenter for a move the user
            // just made.
            applied.latitude = centre.latitude
            applied.longitude = centre.longitude
            applied.zoom = mapView.zoomLevelDouble
            applied.orientation = mapView.mapOrientation.toDouble()
            // Later events of this same gesture at the same place are not
            // news either.
            applied.echoLatitude = centre.latitude
            applied.echoLongitude = centre.longitude
            applied.echoZoom = applied.zoom
            applied.echoOrientation = applied.orientation
            state.updateSpatial(
                latitude = centre.latitude,
                longitude = centre.longitude,
                zoom = mapView.zoomLevelDouble,
                orientation = mapView.mapOrientation.toDouble(),
                source = "map",
                now = System.currentTimeMillis(),
            )
        }

        val listener = object : org.osmdroid.events.MapListener {
            override fun onScroll(event: org.osmdroid.events.ScrollEvent?): Boolean {
                if (isOurOwnMove()) return false
                // A manual pan demotes tracking instead of stopping GPS —
                // the fixes keep coming, the map just stops following.
                if (locationTracking == LocationTracking.Active) {
                    // Exploring: the map parks (following would yank it
                    // back mid-read), but captures keep geotagging from
                    // the fix until the claim is accepted.
                    locationTracking = LocationTracking.Background
                }
                if (!manualClaimed) positionPrompt = true
                syncFromMap()
                return false
            }

            override fun onZoom(event: org.osmdroid.events.ZoomEvent?): Boolean {
                if (isOurOwnMove()) return false
                syncFromMap()
                return false
            }
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
    /**
     * True while WE are moving the camera. osmdroid dispatches MapListener
     * events synchronously from inside setCenter/setZoom, i.e. before the
     * call even returns — so a flag around the call is the only reliable
     * "this one is ours" for those; the echo values below catch any that
     * arrive late.
     */
    var pushing = false
    // What state last asked for — diffed against state so recompositions
    // do not re-issue camera calls (re-issuing restarts tile loading).
    var latitude = Double.NaN
    var longitude = Double.NaN
    var zoom = Double.NaN
    var orientation = Double.NaN

    // What the MapView actually reads back after our own push. The map
    // quantizes coordinates to its pixel grid (setCenter(50.115) reads
    // back as 50.11521), so echo detection must compare against the
    // readback, never the request.
    var echoLatitude = Double.NaN
    var echoLongitude = Double.NaN
    var echoZoom = Double.NaN
    var echoOrientation = Double.NaN

    /**
     * False until the echoes were read from a laid-out view. Pushes made
     * before the first layout read back garbage (the projection has no
     * size), and comparing events against garbage classified osmdroid's own
     * first-layout settle as a user pan.
     */
    var echoValid = false
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
