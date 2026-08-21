package cz.hillview.map

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
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
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlin.math.roundToInt
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

/**
 * The orientation map, ported control-for-control from the Tauri app —
 * see docs/tauri-map-ui-contract.md, which is the spec this follows.
 */
@Composable
actual fun MapScreen(
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
    stateHolder: MapStateHolder,
    stateStore: MapStateStore,
    session: MapSession,
    showControls: Boolean,
) {
    val context = LocalContext.current
    val mapSettings by settings.settings.collectAsState()
    val markers by markerSource.markers.collectAsState()

    // The original's enableLocationTracking runs through the geolocation
    // plugin, which raises the OS permission dialog on first use — here the
    // location button does the asking (nothing on this screen needs it
    // sooner, and an unprompted dialog on open would be a divergence).
    val locationPermission = cz.hillview.core.permissions.rememberPermissionsState(
        permissions = listOf(android.Manifest.permission.ACCESS_FINE_LOCATION),
    )

    // The process-wide holder (restored from the store at first injection),
    // so the bearing survives backgrounding and restarts — the Appium suite
    // asserts it is unchanged after the app comes back — and so capture's
    // follow-me and this map are moving the SAME camera.
    val state = stateHolder
    val spatial by state.spatial.collectAsState()
    val bearing by state.bearing.collectAsState()

    // Hunter mode and the filter override moved OUT of this screen: the
    // viewer pane reads the same two flags to decide what you can turn to,
    // so they are shared state now (see MapFilterState).
    val filters: MapFilterState = org.koin.compose.koinInject()
    val hunterMode by filters.hunterMode.collectAsState()

    // Session-only, exactly as in the Svelte app — but held in MapSession
    // rather than the composition, because the map is its own destination
    // here and a trip through capture would otherwise reset it.
    //
    // READ-ONLY here, and deliberately so. This screen used to keep its own
    // copy of both intents and mirror them back to the session in effects,
    // so the same intent had two homes and either could win: the write-back
    // carried the value read when the composition started, which is stale
    // the moment anything else arms tracking in the same frame (entering
    // capture does exactly that, from MainScreen, which composes first).
    // Whether that race ever fired in practice was never demonstrated — it
    // is removed because one intent with two writers is not a thing to
    // reason about, not because a bug was pinned on it. The session
    // outlives the composition, so the session owns it.
    val trackingWanted by session.bearingTrackingWanted.collectAsState()
    // The phase belongs to the session for the same reason the intent
    // does: it outlives this composition, and the capture pane's debug
    // readout has to be able to see it.
    val trackingPhase by session.bearingPhase.collectAsState()
    val locationTracking by session.locationTracking.collectAsState()
    var locationFlash by remember { mutableStateOf(false) }
    // A pan happened and no manual position is claimed: exploration is
    // free, and this offers the two exits — claim this position, or snap
    // back to the fix. No timeout: reading a map takes as long as it
    // takes.
    var positionPrompt by remember { mutableStateOf(false) }
    val manualClaimed by session.manualPositionClaimed.collectAsState()
    val manualPositionElected by session.manualPositionElected.collectAsState()
    val overrideFilters by filters.overrideFilters.collectAsState()
    var showFilters by remember { mutableStateOf(false) }
    // The toggle panel enumerates whatever sources the composite carries
    // (device + hillview today; mapillary/panoramax join when their
    // loaders are wired). Overrides persist in map settings; absent =
    // the source's default.
    val sourceDescriptors = remember(markerSource) { markerSource.sourceDescriptors() }
    fun sourceEnabled(d: MapSourceDescriptor): Boolean =
        mapSettings.sourceStates[d.id] ?: d.defaultEnabled
    // A photo just taken is in the database but not in the marker set, which
    // is refetched on viewport change — so without this it stays invisible,
    // and out of the viewer's ring, until you happen to pan. The Tauri app
    // covers the same gap with placeholder markers; here the row already
    // exists, so the news is enough. See CaptureEvents.
    val captureEvents: cz.hillview.capture.CaptureEvents = org.koin.compose.koinInject()
    LaunchedEffect(Unit) {
        captureEvents.captured.collect { markerSource.refresh() }
    }

    LaunchedEffect(mapSettings.sourceStates) {
        sourceDescriptors.forEach { d ->
            markerSource.setSourceEnabled(d.id, sourceEnabled(d))
        }
        // A just-enabled source may never have fetched — the gate absorbs
        // any spam.
        markerSource.refresh()
    }
    var arrowTipPx by remember { mutableStateOf(120f) }
    // The front photo: what the gallery would show and the marker drawn as
    // selected. Recomputed from bearing + range, or set by tapping.
    var selectedPhotoId by remember { mutableStateOf<String?>(null) }
    // Published by the marker overlay after each draw that moved anything.
    var markerPositions by remember {
        mutableStateOf<List<Pair<String, Pair<Float, Float>>>>(emptyList())
    }
    val density = LocalDensity.current


    val controller = remember { MapSensorController(context.applicationContext) }
    DisposableEffect(controller) { onDispose { controller.release() } }

    // Bearing tracking: walking runs the compass, car runs GPS orientation.
    // A failed start reverts the user's intent, like the original.
    LaunchedEffect(trackingWanted, mapSettings.bearingMode) {
        if (!trackingWanted) {
            controller.stopBearing()
            session.setBearingPhase(TrackingPhase.Inactive)
            return@LaunchedEffect
        }
        session.setBearingPhase(TrackingPhase.Starting)
        val started = controller.startBearing(mapSettings.bearingMode) { heading, accuracy, magnetic, pitch ->
            session.setBearingPhase(TrackingPhase.Active)
            // Both modes drive the bearing state past a 1° dead-band:
            // walking from the compass, car from the gps-kalman course
            // (mount offset already composed in). The capture stamp reads
            // this same state — Tauri's known-good semantics.
            if (absBearingDiff(heading.toDouble(), state.bearing.value.bearing) > 1.0) {
                state.updateBearing(
                    bearing = heading.toDouble(),
                    source = if (mapSettings.bearingMode == BearingMode.Walking) {
                        "android-compass-true"
                    } else {
                        "gps-kalman"
                    },
                    accuracyLevel = accuracy,
                    // Car mode measures neither, and says so rather than
                    // letting a compass sample ride along under its name.
                    magneticDeg = magnetic,
                    pitch = pitch,
                    now = System.currentTimeMillis(),
                )
            }
        }
        if (!started) {
            // Error then Inactive: the readout catches the Error only if
            // something is watching at that instant, but the log line and
            // the reverted intent survive it.
            session.setBearingPhase(TrackingPhase.Error)
            session.setBearingTrackingWanted(false)
            session.setBearingPhase(TrackingPhase.Inactive)
        }
    }

    // GPS: runs in ACTIVE and BACKGROUND, only ACTIVE moves the map. Also
    // keyed on the permission so a grant mid-session arms the listener the
    // button optimistically asked for.
    LaunchedEffect(locationTracking, locationPermission.granted) {
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

    // The elections, published from here because this pane is always composed
    // (MainScreen renders map and photo side by side, so it is not a
    // navigation destination that can go away). One publisher each, so there
    // is never a moment when two of them disagree about what is primary.
    //
    // Bearing: whichever stream last moved the arrow owns it, as in Tauri.
    LaunchedEffect(bearing.source) {
        controller.publishBearingElection(bearing.source)
    }
    // Location: the map position when the user has said so — through the
    // pill's accepted claim or the capture pane's no-fix hatch — otherwise the
    // fix stream. Electing it also writes it, or the election would point at a
    // source with no rows.
    LaunchedEffect(manualPositionElected, spatial.latitude, spatial.longitude) {
        controller.publishLocationElection(
            manualElected = manualPositionElected,
            latitude = spatial.latitude,
            longitude = spatial.longitude,
        )
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
            session.setBearingTrackingWanted(false)
        }
    }
    arrowOverlay.onBearing = { value ->
        state.updateBearing(value, source = "arrow_drag", now = System.currentTimeMillis())
    }
    arrowOverlay.onBearingDelta = { delta ->
        controller.adjustMountOffset(delta)
        state.updateBearingByDiff(delta, source = "gps-kalman", now = System.currentTimeMillis())
    }
    // The ages are the diagnosis, so they have to keep counting even when
    // nothing else changes — but only while the readout is on screen.
    // When the overlay was last handed a bearing, and which — see
    // GeoDebugText: the arrow can freeze while every other readout moves.
    val arrowStamp = remember { longArrayOf(0L, 0L) }
    val raw by controller.rawOrientation.collectAsState()
    val debugNow by produceState(0L, mapSettings.showGeoDebug) {
        while (mapSettings.showGeoDebug) {
            value = System.currentTimeMillis()
            delay(500)
        }
    }
    val debugLines = if (!mapSettings.showGeoDebug) emptyList() else cz.hillview.geo.geoDebugLines(
        cz.hillview.geo.GeoDebugInput(
            bearing = bearing,
            spatial = spatial,
            bearingWanted = trackingWanted,
            bearingPhase = trackingPhase,
            bearingMode = mapSettings.bearingMode,
            locationTracking = locationTracking,
            rawHeadingDeg = raw?.trueHeading?.toDouble(),
            rawAccuracy = raw?.accuracyLevel,
            rawAtMs = raw?.timestamp,
            rawDetail = raw?.detail,
            rawStillMs = controller.sensorValueStillMs(),
            devicePose = controller.deviceOrientationName(),
            manualPositionClaimed = manualClaimed,
            arrowSetAtMs = arrowStamp[0].takeIf { it != 0L },
            arrowValueDeg = arrowStamp[1].takeIf { arrowStamp[0] != 0L }
                ?.let { Double.fromBits(it) },
            nowMs = debugNow,
        ),
    )

    val mapView = rememberMapView()
    val applied = remember { AppliedCamera() }

    // Sources reload when the map moves — a pan, a zoom, or the GPS follow
    // all write spatial state, exactly the triggers the original's
    // moveend-driven area updates fire on. collectLatest + delay is the
    // debounce: a drag's stream of positions collapses into one reload
    // after the camera settles. Entering the screen emits the current
    // state, so the first load needs no special case (it just waits for
    // the view to have a real bounding box).
    LaunchedEffect(mapSettings.maxPhotos, mapSettings.showUnanalyzed) {
        snapshotFlow { spatial }.collectLatest {
            delay(350)
            while (mapView.width == 0) delay(50)
            val box = mapView.boundingBox
            markerSource.setViewport(
                MapViewport(
                    topLeftLat = box.latNorth,
                    topLeftLon = box.lonWest,
                    bottomRightLat = box.latSouth,
                    bottomRightLon = box.lonEast,
                ),
            )
            markerSource.refresh()
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
                // Not Compose state: written from inside the update block,
                // where a state write would recompose and re-enter it. The
                // readout's own half-second tick is what reads it.
                arrowStamp[0] = System.currentTimeMillis()
                arrowStamp[1] = bearing.bearing.toRawBits()
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
                    filters.revealHiddenPhotos()
                }
                // Greying rule from the contract: outside hunter mode, when
                // featured photos exist, non-featured ones INSIDE the range
                // circle are washed out (outside it they are not).
                // Disabled sources are already excluded by the composite.
                val visible = markers
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

        // Float mode draws the map and nothing else — at PiP size these
        // controls cover most of the window and are far too small to hit.
        if (showControls) MapOverlayUi(
            settings = mapSettings,
            hunterMode = hunterMode,
            sources = sourceDescriptors.map { d ->
                MapSourceUi(id = d.id, name = d.name, enabled = sourceEnabled(d))
            },
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
            debugLines = debugLines,
            onToggleHunterMode = { filters.toggleHunterMode() },
            onToggleSource = { id ->
                settings.update { s ->
                    val d = sourceDescriptors.find { it.id == id }
                    val current = s.sourceStates[id] ?: (d?.defaultEnabled ?: true)
                    s.copy(sourceStates = s.sourceStates + (id to !current))
                }
            },
            onOpenFilters = { showFilters = true },
            onToggleOverrideFilters = { filters.toggleOverrideFilters() },
            currentTileProvider = mapSettings.tileProviderKey,
            onPickTileProvider = { key -> settings.update { it.copy(tileProviderKey = key) } },
            onToggleLocation = {
                session.setLocationTracking(when (locationTracking) {
                    // ACTIVE or BACKGROUND both turn fully off.
                    LocationTracking.Active, LocationTracking.Background -> LocationTracking.Off
                    LocationTracking.Off -> {
                        // Optimistic, like the original: tracking arms now,
                        // fixes start once the user grants (the location
                        // effect re-runs on the grant).
                        if (!locationPermission.granted) {
                            if (locationPermission.permanentlyDenied) {
                                locationPermission.openAppSettings()
                            } else {
                                locationPermission.request()
                            }
                        }
                        LocationTracking.Active
                    }
                })
            },
            onToggleTracking = { session.setBearingTrackingWanted(!trackingWanted) },
            onSelectBearingMode = { mode ->
                // Picking a mode stops the old tracker and starts the new
                // one — enabling tracking is a deliberate side effect of the
                // choice, not something the user has to do afterwards.
                session.setBearingTrackingWanted(false)
                settings.update { it.copy(bearingMode = mode) }
                session.setBearingTrackingWanted(true)
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
                session.setLocationTracking(LocationTracking.Active)
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
                    session.setLocationTracking(LocationTracking.Background)
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
            // The overlay's zoom buttons are the only zoom buttons — the
            // original restyles Leaflet's own control into that role; two
            // sets (osmdroid's fade-in pair appearing on touch) is a bug.
            zoomController.setVisibility(
                org.osmdroid.views.CustomZoomButtonsController.Visibility.NEVER,
            )
            // osmdroid's fling glides essentially unbounded — a fast pan
            // sails the camera far off the map the user was reading, where
            // Leaflet's inertia is short and friction-heavy. Off is the
            // closest match to the original's controlled feel.
            isFlingEnabled = false
            // The map panel is movableContent in MainScreen — a rotation
            // RE-PARENTS this view between the portrait Column and the
            // landscape Row instead of rebuilding it. osmdroid's default
            // (destroy mode ON) runs onDetach() — tile provider and overlays
            // torn down — on every onDetachedFromWindow, which would leave a
            // dead map after the first rotation. Teardown belongs to the
            // composition leaving, which the DisposableEffect below owns.
            setDestroyMode(false)
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
    // Mount offset and the heading-filter reset still go through the manager;
    // the STREAMS come from the engine now.
    private val geoTracking by lazy { GeoTrackingManager.get(context) }

    // This pane no longer opens hardware. It observes the ONE owner — see
    // docs/frontend2-geo-engine-design.md; three owners is how the app ended
    // up with a compass reading that was not the app's.
    private val engine by lazy { cz.hillview.geo.GeoEngine.get(context) }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var compassJob: Job? = null
    private var carJob: Job? = null
    private var fixJob: Job? = null

    /**
     * The engine's heading BEFORE election, for the debug readout: the
     * question it answers is whether a still readout means a still phone or
     * a chain that stopped writing, and only the raw side can say.
     */
    val rawOrientation get() = engine.orientation

    /** How long the attitude sample has been repeating — see GeoEngine. */
    fun sensorValueStillMs(): Long? = engine.sensorValueStillMs()

    /** The pose class the UPRIGHT remap keys on — see GeoDebugText. */
    fun deviceOrientationName(): String? = engine.deviceOrientationName()

    fun compassAvailable(): Boolean =
        (context.getSystemService(Context.SENSOR_SERVICE) as android.hardware.SensorManager)
            .getDefaultSensor(android.hardware.Sensor.TYPE_ROTATION_VECTOR) != null

    /**
     * Hand the tracking tables the elected bearing source, mapped to their
     * coarse vocabulary — the same rule as toTableSource() in the Tauri app's
     * mapState.ts, minus the IPC boundary that forced it to live in JS there.
     */
    fun publishBearingElection(source: String) {
        geoTracking.setElectedBearingSource(
            when {
                source == "gps-kalman" -> "gps-kalman"
                source.startsWith("android") -> "android"
                else -> "manual"
            }
        )
    }

    private var lastLocationElection: String? = null

    /**
     * Hand over the elected location source, and — while the map position is
     * the elected one — write it as a real row, so the election never names a
     * source with nothing in it. Tauri gets the row for free because a pan
     * writes one anyway; here the electing act has to.
     *
     * The name is only pushed when it changes (this is driven by map movement,
     * which is continuous); the row follows the position, as a pan should.
     */
    fun publishLocationElection(manualElected: Boolean, latitude: Double, longitude: Double) {
        val elected = if (manualElected) "manual" else "android"
        if (elected != lastLocationElection) {
            lastLocationElection = elected
            geoTracking.setElectedLocationSource(elected)
        }
        if (manualElected) {
            geoTracking.storeLocationNamed(
                timestamp = System.currentTimeMillis(),
                latitude = latitude,
                longitude = longitude,
                source = "manual",
                detail = "map",
            )
        }
    }

    private var carHeading: ((Float, Int?, Double?, Double?) -> Unit)? = null
    private var wantLocation = false
    private var wantCar = false
    private var onFix: ((Double, Double) -> Unit)? = null

    /** @return false when the stream cannot be observed (reverts intent). */
    fun startBearing(
        mode: BearingMode,
        /** heading, accuracy, magnetic heading, pitch — one sample, not four reads. */
        onHeading: (Float, Int?, Double?, Double?) -> Unit,
    ): Boolean {
        stopBearing()
        return when (mode) {
            BearingMode.Walking -> {
                if (!compassAvailable()) return false
                compassJob = scope.launch {
                    engine.orientation.collect { data ->
                        data?.let {
                            onHeading(
                                it.trueHeading,
                                it.accuracyLevel,
                                it.magneticHeading.toDouble(),
                                it.pitch.toDouble(),
                            )
                        }
                    }
                }
                true
            }
            BearingMode.Car -> {
                // The Tauri car flow. The COMPOSITION (fix → Kalman → mount
                // offset) now happens in the engine, on its own thread —
                // this pane only observes the result, so a heavy marker pass
                // can no longer delay the value a capture stamps.
                if (!engine.hasLocationPermission()) return false
                engine.resetCarHeadingFilter()
                carJob = scope.launch {
                    // No magnetic heading and no pitch: a GPS course knows
                    // neither, and null is what that means.
                    engine.carBearing.collect { onHeading(it.toFloat(), null, null, null) }
                }
                wantCar = true
                syncLocation()
                true
            }
        }
    }

    fun stopBearing() {
        compassJob?.cancel()
        compassJob = null
        carJob?.cancel()
        carJob = null
        carHeading = null
        if (wantCar) {
            wantCar = false
            syncLocation()
        }
    }

    fun setLocationEnabled(enabled: Boolean, onFix: (Double, Double) -> Unit) {
        wantLocation = enabled
        if (enabled) this.onFix = onFix
        syncLocation()
    }

    /**
     * Follow-me's subscription to the engine's fix stream. The engine is not
     * started or stopped here — the ACTIVITY decides that (MainScreen hands
     * it a GeoConfig); this only says whether the map wants to hear about
     * fixes. Declination, table rows and the Kalman composition all happen
     * in the engine, once, for every consumer.
     */
    private fun syncLocation() {
        val want = wantLocation || wantCar
        if (!want) {
            fixJob?.cancel()
            fixJob = null
            return
        }
        if (fixJob != null) return
        fixJob = scope.launch {
            engine.location.collect { fix ->
                if (wantLocation && fix != null) onFix?.invoke(fix.latitude, fix.longitude)
            }
        }
    }

    /** Car mode: the drag moves the camera mount, not the heading. */
    fun adjustMountOffset(deltaDeg: Double) {
        geoTracking.setMountOffset(geoTracking.getMountOffset() + deltaDeg)
    }

    fun release() {
        stopBearing()
        setLocationEnabled(false) { _, _ -> }
        scope.cancel()
    }

    private fun hasLocationPermission() =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
}
