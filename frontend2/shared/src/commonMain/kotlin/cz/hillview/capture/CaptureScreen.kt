package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import cz.hillview.upload.PendingUpload
import cz.hillview.upload.UploadPipeline
import kotlinx.coroutines.delay
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.core.nowMs
import kotlin.math.roundToInt
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.TimeSource

// The two glass families every original overlay uses: dark pills for info
// and actions (rgba(0,0,0,.5–.7) in the CSS), white glass for the utility
// buttons (rgba(255,255,255,.2)). One constant each — the pane had drifted
// into five different alphas of black (phone-in-hand feedback: unify).
// The location pill is NOT in either family: its six-level white cycle is
// the ported CameraOverlay contract.
internal val DarkGlass = Color(0xB3000000)
internal val LightGlass = Color(0x33FFFFFF)

// The ladder itself — its rungs, its labels and the geometry the gesture
// reads — lives in IntervalLadder.kt. Video is one of its rungs because
// video is a modality of this pane ("almost just a 0-interval photo
// capture"), chosen the same way a run is: hold, slide up, release.

/**
 * Session totals for the corner indicator — the original's captureQueue
 * stats singleton lives for the webview session; a process-wide object is
 * the same lifetime here: it survives pane bounces and navigation and
 * resets with the app.
 */
internal object CaptureSessionCounters {
    val totalCaptured = androidx.compose.runtime.mutableStateOf(0)
}

@Composable
fun CaptureScreen(
    onOpenSettings: () -> Unit = {},
    uploadPipeline: UploadPipeline = org.koin.compose.koinInject(),
    uploadSettingsRepo: cz.hillview.settings.UploadSettingsRepository =
        org.koin.compose.koinInject(),
) {
    val capture = rememberPhotoCapture()
    val state = capture.state
    val queueStats by uploadPipeline.stats.collectAsState()
    val uploadSettings by uploadSettingsRepo.settings.collectAsState()
    val sessionManager: cz.hillview.auth.SessionManager = org.koin.compose.koinInject()
    val sessionState by sessionManager.state.collectAsState()

    // The lifted-gate state now lives on the session (see
    // MapSession.mapPositionWithoutFix) — it decides what reaches the tracking
    // tables, so it has to be answerable while this pane is closed.
    // The LIVE map state — the same holder the always-mounted map pane
    // renders, so follow-me and the claim move the camera the user is
    // looking at (a store write would go behind the mounted map's back).
    val mapState: cz.hillview.map.MapStateHolder = org.koin.compose.koinInject()
    val mapSettingsRepo: cz.hillview.settings.MapSettingsRepository = org.koin.compose.koinInject()
    val mapSettings by mapSettingsRepo.settings.collectAsState()
    val session: cz.hillview.map.MapSession = org.koin.compose.koinInject()
    val locationTracking by session.locationTracking.collectAsState()
    val manualClaimed by session.manualPositionClaimed.collectAsState()
    val mapPositionWithoutFix by session.mapPositionWithoutFix.collectAsState()
    val manualElected by session.manualPositionElected.collectAsState()

    // A claimed manual position (accepted on the map) overrides the fix:
    // captures geotag from the map centre, tagged "manual" — and the
    // degraded shutter tone says so out loud.
    // Two deliberate acts elect the map position, and nothing else does: the
    // pill's accepted claim and the no-fix escape hatch below. The session
    // combines them into one answer; this only mirrors it onto the capture
    // object so a shutter press knows what to stamp. A stale fix quietly
    // taking over used to be a third, unspoken act.
    LaunchedEffect(manualElected) {
        capture.manualLocationElected = manualElected
    }
    // BACKGROUND tracking = exploring: the map is parked off the fix. The
    // other half of what altLocationFor needs.
    LaunchedEffect(locationTracking) {
        capture.exploring = locationTracking == cz.hillview.map.LocationTracking.Background
    }
    // The stamp position is the map's centre, LIVE — same shape as the stamp
    // bearing below, and the same as Tauri, whose locationData is reactive on
    // $spatialState. It was previously read once at the electing moment, so
    // claiming at one place, panning to another and shooting stamped the
    // first while the tracking table recorded the second: the photo and the
    // log disagreed about where the user said they were. Always populated;
    // manualLocationElected alone decides whether anything reads it.
    LaunchedEffect(Unit) {
        mapState.spatial.collect { s ->
            capture.manualLocation = ManualLocation(s.latitude, s.longitude, s.ts)
        }
    }
    // The capture stamp bearing IS the map's bearing state (Tauri:
    // locationData.bearing = bearingState.bearing): car mode's
    // gps-kalman + mount offset, walking's compass, or the hand-set
    // arrow — whichever currently owns the arrow.
    LaunchedEffect(Unit) {
        mapState.bearing.collect { b ->
            // The whole answer, not just its heading: the pane has no sensor
            // of its own to fill in the rest from.
            capture.stampBearing = StampBearing(
                trueDeg = b.bearing.toFloat(),
                source = b.source,
                magneticDeg = b.magneticDeg,
                pitch = b.pitch,
                accuracyLevel = b.accuracyLevel,
            )
        }
    }

    var showCalibration by rememberSaveable { mutableStateOf(false) }
    var showResolutionMenu by rememberSaveable { mutableStateOf(false) }
    var showShutterMenu by rememberSaveable { mutableStateOf(false) }

    // The persisted pin re-applies whenever the camera is (re)bound —
    // selectResolution dedups, so this cannot rebind-loop.
    LaunchedEffect(mapSettings.captureResolution, state.ready) {
        val parsed = mapSettings.captureResolution
            ?.split("x")
            ?.takeIf { it.size == 2 }
            ?.let { (w, h) ->
                w.toIntOrNull()?.let { wi ->
                    h.toIntOrNull()?.let { hi -> CaptureResolution(wi, hi) }
                }
            }
        capture.selectResolution(parsed)
    }
    // Same shape: the still-capture mode and JPEG quality are build options
    // of the ImageCapture, persisted like the resolution pin; configureStill
    // dedups, so re-running on ready cannot rebind-loop either.
    LaunchedEffect(mapSettings.stillCaptureMode, mapSettings.jpegQuality, state.ready) {
        capture.configureStill(mapSettings.stillCaptureMode, mapSettings.jpegQuality)
    }

    // Eco effects apply only while this screen is up — the composition IS
    // the activity gate the Tauri `powerSavingActive` derives. The slider's
    // 30 means "the untouched default": no throttle even with eco on.
    val ecoActive = mapSettings.powerSavingPref
    LaunchedEffect(ecoActive, mapSettings.ecoFps) {
        capture.ecoPreviewFps =
            if (ecoActive && mapSettings.ecoFps < 30f) mapSettings.ecoFps else null
    }

    // The map follows the fixes while tracking is ACTIVE — live through the
    // shared holder, so the mounted map pane moves as the fixes come in —
    // except under eco, where it only catches up at each capture (the whole
    // point of the toggle).
    fun followMapTo(latitude: Double, longitude: Double) {
        mapState.updateSpatial(
            latitude = latitude,
            longitude = longitude,
            source = "gps",
            now = cz.hillview.core.nowMs(),
        )
    }
    LaunchedEffect(state.fixLatitude, state.fixLongitude, ecoActive, locationTracking) {
        val lat = state.fixLatitude ?: return@LaunchedEffect
        val lon = state.fixLongitude ?: return@LaunchedEffect
        if (locationTracking == cz.hillview.map.LocationTracking.Active && !ecoActive) {
            followMapTo(lat, lon)
        }
    }

    // The after-capture auto-upload prompt: shown once a capture lands while
    // auto-upload is off, unless the user chose "never". Session-dismissed
    // so it cannot nag a rapid-fire run.
    var promptVisible by rememberSaveable { mutableStateOf(false) }
    var promptDismissed by rememberSaveable { mutableStateOf(false) }

    // Tauri auto-hides the card after 12 s (only the × sets the session
    // dismissal — a timed-out prompt may return after the next capture).
    LaunchedEffect(promptVisible) {
        if (promptVisible) {
            delay(12_000)
            promptVisible = false
        }
    }

    // The rung a release would commit to, as an index into INTERVAL_LADDER;
    // it survives the gesture, so a stopped run remembers its own speed.
    // repeating is the running-run flag.
    var intervalIndex by rememberSaveable { mutableStateOf(0) }
    var repeating by rememberSaveable { mutableStateOf(false) }
    var runCount by remember { mutableStateOf(0) }

    // The ⚡ menu edits a target and a bias whether or not a rule is in
    // force, so switching back off Auto returns to what was last set up
    // rather than to a default. 1/500 is the middle of the ladder.
    var exposureTargetNs by rememberSaveable { mutableStateOf(2_000_000L) }
    var exposureBias by rememberSaveable { mutableStateOf(0.0) }

    // A MOTION shoot under Auto defaults to Sports (user-decided): an
    // interval run and a video are both walking or driving shoots, where
    // motion blur is the failure mode and Sports is the rule built for
    // exactly that. Only when the rule IS Auto — Pin/Floor/Sports picked by
    // hand is the user's choice and survives untouched — and only for the
    // shoot's lifetime. The identity check (===) on the way out means even
    // re-picking identical Sports values mid-shoot counts as an explicit
    // choice and is kept.
    fun engageSportsIfAuto(): ExposureRule? =
        if (capture.exposureRule == null && capture.state.manualShutterSupported) {
            ExposureRule(ExposureMode.Sports, exposureTargetNs, exposureBias)
                .also { capture.exposureRule = it }
        } else {
            null
        }
    fun standDownSports(engaged: ExposureRule?) {
        if (engaged != null && capture.exposureRule === engaged) capture.exposureRule = null
    }

    // Video inherits the default. Engaged at the ladder release, BEFORE
    // startVideo (its rebind re-applies the request options, so the first
    // frames already carry the rule); stood down when the recording ends,
    // whichever way it ends.
    var videoEngaged by remember { mutableStateOf<ExposureRule?>(null) }
    LaunchedEffect(state.recording) {
        if (!state.recording) {
            standDownSports(videoEngaged)
            videoEngaged = null
        }
    }

    LaunchedEffect(repeating, intervalIndex) {
        val runRung = INTERVAL_LADDER.getOrNull(intervalIndex) as? LadderRung.Every
        if (!repeating || runRung == null) {
            // The original zeroes its badge when the run stops.
            runCount = 0
            return@LaunchedEffect
        }
        val engaged = engageSportsIfAuto()
        try {
        // An ABSOLUTE timeline. The loop used to sleep a fixed interval
        // AFTER each shot, so the real period was "interval + however long
        // issuing the shot took" and the error accumulated — a run could
        // only ever slide later, never correct. Targets are computed from
        // the run's start instead, so a slow shot is absorbed rather than
        // added to every shot after it.
        val interval = runRung.ms.milliseconds
        val clock = TimeSource.Monotonic.markNow()
        var nextAt = Duration.ZERO
        while (true) {
            // The previous shot may still be in flight. WAIT for it and
            // then fire — the beat is late, not cancelled (user's choice:
            // under load, density beats regularity).
            //
            // capture.state is re-read here deliberately: `state` above is
            // the value captured at composition, so the old
            // `if (!state.capturing)` guard was testing launch-time data
            // and never actually withheld anything.
            while (capture.state.capturing) delay(15)
            // Metering is continuous now, so this is free — it only costs a
            // window on hardware that refused the analysis stream.
            capture.prepareExposure()
            capture.capture()
            runCount++
            nextAt += interval
            val now = clock.elapsedNow()
            if (now >= nextAt) {
                // Behind schedule: go again immediately, and re-base so the
                // debt cannot accumulate into a rapid-fire burst when the
                // phone recovers. Counted, because a run that is quietly
                // late is exactly what thermal throttling looks like.
                CaptureStatsLog.increment("interval behind", nowMs())
                nextAt = now
            } else {
                delay(nextAt - now)
            }
        }
        } finally {
            // The run's engagement ends with the run — the effect is
            // cancelled when `repeating` flips false, so this is the stop
            // path (and the leave-the-screen path) in one place.
            standDownSports(engaged)
        }
    }

    // Every capture goes straight into the offline-first pipeline; it no-ops
    // when logged out and the entry survives for auto-upload-on-login.
    LaunchedEffect(state.lastPhoto) {
        val photo = state.lastPhoto ?: return@LaunchedEffect
        CaptureSessionCounters.totalCaptured.value++
        uploadPipeline.onPhotoCaptured(
            PendingUpload(
                id = photo.path,
                filePath = photo.path,
                filename = photo.filename,
                latitude = photo.snapshot.latitude,
                longitude = photo.snapshot.longitude,
                altitude = photo.snapshot.altitude,
                // True heading — the DB/authorize bearing is true north
                // everywhere in the pipeline (see SensorSnapshot).
                bearing = photo.snapshot.trueBearingDeg?.toDouble(),
                capturedAtMs = photo.snapshot.capturedAtMs,
                // The provenance lives in the ROW from here on — in the
                // fast-write default the file has no EXIF, so this is the
                // stamp's only vehicle to the upload metadata.
                bearingSource = photo.snapshot.bearingSource,
                locationSource = photo.snapshot.locationSource,
                locationAgeMs = photo.snapshot.locationAgeMs,
                exposureJson = photo.snapshot.exposure?.let { exposureProvenanceJson(it) },
                pitchDeg = photo.snapshot.pitchDeg?.toDouble(),
                altLocationJson = photo.snapshot.altLocation?.let { altLocationJson(it) },
                // Snapshot, not a live read — see PendingUpload.license.
                license = uploadSettings.license,
            )
        )
        // Under eco the map catches up here, once per capture — Tauri's
        // "power saving: map catches up after each capture".
        //
        // ECO ONLY, and it catches up to the LATEST FIX, not to the
        // photo's own stamp. Ungated it fought the live follow above, and
        // the stamp is shutter-time news: `lastPhoto` only publishes after
        // the EXIF whole-file rewrite, so pushing it rewound the camera
        // onto the photo just taken — and, because a spatial write is what
        // triggers the marker reload, it did so at the exact moment that
        // photo's marker appeared — until the next fix pulled it forward.
        val catchUpLat = state.fixLatitude
        val catchUpLon = state.fixLongitude
        if (ecoActive &&
            locationTracking == cz.hillview.map.LocationTracking.Active &&
            catchUpLat != null && catchUpLon != null
        ) {
            followMapTo(catchUpLat, catchUpLon)
        }

        // The original waits 800 ms after the shutter before prompting, "to
        // avoid UI confusion" right at the moment of capture. Its trigger:
        // (!authed || !autoUploadEnabled) — a logged-out user gets it even
        // with the switch on, because logged out means uploads CANNOT run.
        if ((!uploadSettings.autoUploadEnabled ||
                sessionState !is cz.hillview.auth.SessionState.LoggedIn) &&
            uploadSettings.autoUploadPromptEnabled &&
            !promptDismissed
        ) {
            delay(800)
            promptVisible = true
        }
    }

    // Stats poll for pipelines that derive stats from external state (the
    // shared-kt stack uploads in WorkManager, off this screen's call path).
    LaunchedEffect(Unit) {
        while (true) {
            uploadPipeline.refreshStats()
            delay(2_000)
        }
    }

    // Pane-scope, not cluster-scope: the catch-zone wash below and the
    // shutter cluster both need these. What releasing RIGHT NOW would do
    // (null = cancel) used to live only inside the gesture loop
    // (overLadder), so the one fact the whole gesture turns on was the one
    // fact the screen could not show — and a run kept starting, or not, by
    // surprise (user-raised: "i keep missing it").
    var ladderVisible by remember { mutableStateOf(false) }
    var armedIndex by remember { mutableStateOf<Int?>(null) }
    // Where the finger is on the scale RIGHT NOW, whether or not it is over
    // the catch zone yet: the rung it is level with, and the exact fraction
    // for the pointer line. Separate from armedIndex because "what I am
    // pointing at" and "what releasing would do" are different answers while
    // the thumb is still on the button.
    var hoverIndex by remember { mutableStateOf(0) }
    var pointerFraction by remember { mutableStateOf<Float?>(null) }
    // What releasing would commit to, as a rung — the shutter previews it.
    val armedRung = armedIndex?.let { INTERVAL_LADDER.getOrNull(it) }
    // Why the last shutter press did nothing, shown briefly in the status
    // line. A press that is silently ignored is indistinguishable from a
    // dead button (field report: "does not react to long press anymore
    // until I restart"); this makes the two look different.
    var ignoredPress by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(ignoredPress) {
        if (ignoredPress != null) {
            delay(2_500)
            ignoredPress = null
        }
    }
    var circleBounds by remember { mutableStateOf<Rect?>(null) }
    var paneOrigin by remember { mutableStateOf(Offset.Zero) }
    // The ladder spans the pane, so the pane's own rect is the scale the
    // gesture reads. One rect for both, which is the property the old
    // fixed-height slider did not have.
    var paneBounds by remember { mutableStateOf<Rect?>(null) }

    // The capture pane IS the camera stream — the original's camera-content
    // fills with the video and positions every control absolutely over it
    // (CameraCapture.svelte styles). No control rows under the video, no
    // scroll column. (Round-4 phone-in-hand feedback: the previous cut kept
    // a letterboxed preview above a stack of visible controls.)
    Box(
        modifier = Modifier
            .onGloballyPositioned {
                paneOrigin = it.positionInRoot()
                paneBounds = it.boundsInRoot()
            }
            .fillMaxSize()
            .background(Color.Black),
    ) {
        capture.CameraPane(Modifier.fillMaxSize())

        // Top-left stack near the original pill's spot (CameraOverlay
        // .svelte: top 60px / left 60px) — pulled LOWER than the original's
        // 60: Main's floating hamburger/camera row is taller than the
        // Tauri one and was eating the pill's first line (phone-in-hand).
        // The status and upload lines are this port's extension; they ride
        // under the pill as glass strips instead of claiming pane rows.
        Column(
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(start = 60.dp, top = 88.dp, end = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            horizontalAlignment = Alignment.Start,
        ) {
            // "Why is the heading not moving?" — because the compass is not
            // driving the app's bearing, which is a state the pane must
            // EXPLAIN rather than merely reflect. The capture readout shows
            // mapState.bearing (the value a photo would be stamped with), so
            // with tracking off it is legitimately frozen, and the original
            // answers exactly this with its bearing-tracking hint.
            val bearingTrackingOn by session.bearingTrackingWanted.collectAsState()
            val showBearingHint = !bearingTrackingOn && !mapSettings.hideBearingTrackingHint
            if (showBearingHint) {
                BearingTrackingHint(
                    onEnable = { session.setBearingTrackingWanted(true) },
                    onDismiss = {
                        mapSettingsRepo.update { it.copy(hideBearingTrackingHint = true) }
                    },
                )
            }

            CameraOverlayUi(
                suppressHint = showBearingHint,
                state = state,
                bearingMode = mapSettings.bearingMode,
                overridePosition = if (capture.manualLocationElected) capture.manualLocation else null,
                opacityLevel = mapSettings.cameraOverlayOpacity,
                onCycleOpacity = {
                    mapSettingsRepo.update {
                        it.copy(cameraOverlayOpacity = nextOverlayOpacity(it.cameraOverlayOpacity))
                    }
                },
                statusText = ignoredPress?.let { "⚠️ press ignored: $it" } ?: statusLineText(state),
                uploadsText = "uploads: ${queueStats.done} done" +
                    (if (queueStats.duplicate > 0) ", ${queueStats.duplicate} dup" else "") +
                    (if (queueStats.pending > 0) ", ${queueStats.pending} pending" else "") +
                    (if (queueStats.failed > 0) ", ${queueStats.failed} failed" else "") +
                    (queueStats.lastError?.let { " · $it" } ?: ""),
            )
        }

        // The Leaf — the original's power-saving-button: a translucent
        // circle below the top-right corner (that corner belongs to the
        // debug toggles there). Lower preview fps, and the map only catches
        // up after each capture instead of chasing every fix. Tap toggles;
        // the shutter's one-finger grammar tunes it: hold 300 ms, the fps
        // slider unfolds beneath, slide onto it, release to set (and arm
        // eco). Bottom = refresh only on capture, then 0.1..30 fps (log),
        // top = the untouched default.
        var ecoSliderVisible by remember { mutableStateOf(false) }
        var ecoT by remember { mutableStateOf(0f) }
        var leafBounds by remember { mutableStateOf<Rect?>(null) }
        var ecoZone by remember { mutableStateOf<Rect?>(null) }
        var ecoOrigin by remember { mutableStateOf(Offset.Zero) }
        Column(
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(top = 52.dp, end = 8.dp)
                .onGloballyPositioned { ecoOrigin = it.positionInRoot() }
                .pointerInput(Unit) {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        val leaf = leafBounds ?: return@awaitEachGesture
                        if (!leaf.contains(ecoOrigin + down.position)) return@awaitEachGesture
                        down.consume()
                        val quick = withTimeoutOrNull(300L) {
                            if (waitForUpOrCancellation() != null) "tap" else "cancel"
                        }
                        if (quick == "tap") {
                            mapSettingsRepo.update { it.copy(powerSavingPref = !it.powerSavingPref) }
                            return@awaitEachGesture
                        }
                        if (quick == "cancel") return@awaitEachGesture
                        ecoT = ecoFpsToSlider(mapSettings.ecoFps)
                        ecoSliderVisible = true
                        var overSlider = false
                        try {
                            while (true) {
                                val event = awaitPointerEvent()
                                val change = event.changes.firstOrNull { it.id == down.id }
                                    ?: event.changes.first()
                                val pos = ecoOrigin + change.position
                                val zone = ecoZone
                                // Everything below the leaf is the catch zone.
                                overSlider = pos.y > leaf.bottom
                                if (overSlider && zone != null && zone.height > 0f) {
                                    ecoT = (1f - (pos.y - zone.top) / zone.height)
                                        .coerceIn(0f, 1f)
                                }
                                change.consume()
                                if (event.changes.none { it.pressed }) {
                                    if (overSlider) {
                                        // Choosing a level IS choosing eco.
                                        mapSettingsRepo.update {
                                            it.copy(
                                                ecoFps = ecoSliderToFps(ecoT),
                                                powerSavingPref = true,
                                            )
                                        }
                                    }
                                    break
                                }
                            }
                        } finally {
                            ecoSliderVisible = false
                        }
                    }
                },
        ) {
            Box(
                modifier = Modifier
                    .size(38.dp)
                    .clip(CircleShape)
                    .background(if (ecoActive) Color(0xCC2EA043) else LightGlass)
                    .onGloballyPositioned { leafBounds = it.boundsInRoot() }
                    // Touch runs through the container's gesture; semantics
                    // keep the click contract for tests and accessibility.
                    .semantics {
                        role = Role.Button
                        onClick(label = null) {
                            mapSettingsRepo.update { it.copy(powerSavingPref = !it.powerSavingPref) }
                            true
                        }
                    }
                    .testTag("power-saving-btn"),
                contentAlignment = Alignment.Center,
            ) { Text("🍃") }
            if (ecoSliderVisible) {
                EcoSlider(t = ecoT, onTrackPositioned = { ecoZone = it })
            }
        }

        // Click-away for the two corner menus, as the original's camera
        // dropdown closes on outside interaction — an invisible catcher
        // under the menus, above the video.
        if (showResolutionMenu || showShutterMenu) {
            Box(
                Modifier
                    .fillMaxSize()
                    .clickable(
                        interactionSource = remember {
                            androidx.compose.foundation.interaction.MutableInteractionSource()
                        },
                        indication = null,
                    ) {
                        showResolutionMenu = false
                        showShutterMenu = false
                    },
            )
        }

        // The 📷 selector, lower-left as in Tauri. Only resolutions for
        // now; the camera rows join when enumeration is ported.
        if (state.availableResolutions.isNotEmpty()) {
            Column(Modifier.align(Alignment.BottomStart).padding(start = 8.dp, bottom = 6.dp)) {
                if (showResolutionMenu) {
                    Column(
                        Modifier
                            .background(
                                Color(0xDD222222),
                                RoundedCornerShape(8.dp),
                            )
                            .padding(4.dp)
                            // Resolutions + focus outgrow a split pane.
                            .heightIn(max = 400.dp)
                            .verticalScroll(rememberScrollState())
                            .testTag("camera-selector-dropdown"),
                    ) {
                        ResolutionOption(
                            label = "Auto (max quality)",
                            selected = state.selectedResolution == null,
                            tag = "resolution-option-auto",
                        ) {
                            showResolutionMenu = false
                            mapSettingsRepo.update { it.copy(captureResolution = null) }
                        }
                        // The sensor can offer dozens; the biggest few
                        // are the ones anyone picks.
                        state.availableResolutions.take(6).forEach { r ->
                            ResolutionOption(
                                label = resolutionLabel(r),
                                selected = state.selectedResolution == r,
                                tag = "resolution-option-${r.width}x${r.height}",
                            ) {
                                showResolutionMenu = false
                                mapSettingsRepo.update {
                                    it.copy(captureResolution = "${r.width}x${r.height}")
                                }
                            }
                        }
                        // Focus, the vista case: Auto (tap-to-focus and the
                        // long-press lock live on the preview itself) or
                        // pinned at infinity. Native-ish divergence — the
                        // original's focus-distance slider was necessity UX.
                        if (state.manualFocusSupported) {
                            Text(
                                "Focus",
                                color = Color(0x99FFFFFF),
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(start = 12.dp, top = 6.dp),
                            )
                            ResolutionOption(
                                label = "Auto",
                                selected = !state.focusInfinity,
                                tag = "focus-option-auto",
                            ) {
                                showResolutionMenu = false
                                capture.focusInfinity = false
                            }
                            ResolutionOption(
                                label = "∞ landscape",
                                selected = state.focusInfinity,
                                tag = "focus-option-infinity",
                            ) {
                                showResolutionMenu = false
                                capture.focusInfinity = true
                            }
                        }
                        // What sits between the press and the exposure —
                        // CameraX's capture mode (see StillCaptureMode:
                        // Quality locks 3A first, the shutter lag the user
                        // feels; Latency does not; ZSL serves an already-
                        // captured frame where the camera can). A knob
                        // because the answer is measured in the field,
                        // with the Stats dialog's press→exposure numbers.
                        Text(
                            "Still capture",
                            color = Color(0x99FFFFFF),
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(start = 12.dp, top = 6.dp),
                        )
                        StillCaptureMode.entries.forEach { mode ->
                            val unsupported =
                                mode == StillCaptureMode.ZeroShutterLag && !state.zslSupported
                            ResolutionOption(
                                label = mode.label +
                                    if (unsupported) " (unsupported here → Latency)" else "",
                                selected = state.stillCaptureMode == mode,
                                tag = "still-mode-option-${mode.key}",
                            ) {
                                showResolutionMenu = false
                                mapSettingsRepo.update { it.copy(stillCaptureMode = mode) }
                            }
                        }
                        // Decoupled from the mode on purpose: CameraX's
                        // default ties them (100 for Quality, 95 otherwise)
                        // and the two trades have nothing to do with each
                        // other.
                        Text(
                            "JPEG quality",
                            color = Color(0x99FFFFFF),
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(start = 12.dp, top = 6.dp),
                        )
                        Row {
                            JPEG_QUALITY_CHOICES.forEach { q ->
                                ResolutionOption(
                                    label = q.toString(),
                                    selected = state.jpegQuality == q,
                                    tag = "jpeg-quality-option-$q",
                                ) {
                                    showResolutionMenu = false
                                    mapSettingsRepo.update { it.copy(jpegQuality = q) }
                                }
                            }
                        }
                    }
                }
                TextButton(
                    onClick = { showResolutionMenu = !showResolutionMenu },
                    modifier = Modifier
                        .background(LightGlass, CircleShape)
                        .testTag("camera-selector-button"),
                ) { Text("📷", style = MaterialTheme.typography.titleMedium) }
            }
        }

        // The lower-right column: the ⚡ shutter-speed control stacked over
        // the original's corner counter (CaptureQueueIndicator, bottom:6
        // right:0 — the counter keeps the very corner).
        Column(
            Modifier.align(Alignment.BottomEnd).padding(end = 8.dp, bottom = 6.dp),
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            // Shutter time, for crisp shots out of a moving vehicle — this
            // port's addition (the original has no manual exposure).
            // Collapsed behind a ⚡ button, expanding upward like the
            // camera selector; the open ladder used to sprawl across the
            // pane (round-4 feedback).
            //
            // Three rows, not one, since a time on its own turned out not
            // to be an instruction: how hard to DEFEND it decides whether
            // the same 1/2000 is a crisp drive-by or three stops of blown
            // sky (see ExposureMode). The rows stay open across taps —
            // picking a rule is now a two- or three-tap act.
            if (state.manualShutterSupported) {
                if (showShutterMenu) {
                    Column(
                        Modifier
                            .background(DarkGlass, RoundedCornerShape(8.dp))
                            .padding(4.dp)
                            .testTag("shutter-speed-menu"),
                    ) {
                        MenuLabel("Rule")
                        Row {
                            ShutterChip(
                                "Auto",
                                state.exposureRule == null,
                                "capture-exposure-auto",
                            ) { capture.exposureRule = null }
                            EXPOSURE_MODES.forEach { mode ->
                                ShutterChip(
                                    exposureModeLabel(mode),
                                    state.exposureRule?.mode == mode,
                                    "capture-exposure-mode-${mode.name.lowercase()}",
                                ) {
                                    capture.exposureRule =
                                        ExposureRule(mode, exposureTargetNs, exposureBias)
                                }
                            }
                        }

                        MenuLabel("Target")
                        Row {
                            SHUTTER_CHOICES_NS.forEach { ns ->
                                ShutterChip(
                                    formatShutter(ns),
                                    exposureTargetNs == ns,
                                    "capture-shutter-${1_000_000_000L / ns}",
                                ) {
                                    exposureTargetNs = ns
                                    // A bare time still means something on
                                    // its own: the rule that survives sun.
                                    capture.exposureRule =
                                        state.exposureRule?.copy(targetNs = ns)
                                            ?: ExposureRule(
                                                ExposureMode.Floor, ns, exposureBias,
                                            )
                                }
                            }
                        }

                        // The bias biases the METERING, so it needs a rule of
                        // ours to ride on — under auto exposure the camera's
                        // own AE owns that decision. Shown ALWAYS, disabled
                        // under Auto, rather than appearing when a rule is
                        // picked: this menu is anchored at its bottom, so a
                        // row materialising here shoves the Rule and Target
                        // chips upward — and the tap after choosing a rule is
                        // usually a target, aimed at where the chip WAS.
                        MenuLabel("Bias")
                        Row {
                            EV_BIAS_CHOICES.forEach { ev ->
                                ShutterChip(
                                    formatEvBias(ev),
                                    state.exposureRule?.evBias == ev,
                                    "capture-exposure-ev-${evTag(ev)}",
                                ) {
                                    exposureBias = ev
                                    // Under Auto this arms the bias for the
                                    // rule you pick next, rather than doing
                                    // nothing and looking broken.
                                    capture.exposureRule = state.exposureRule?.copy(evBias = ev)
                                }
                            }
                        }

                        // What the rule actually resolved to last time it
                        // was applied — the only honest answer to "is this
                        // mode working here?", live, in the field. Always
                        // occupies its line, for the same reason as the bias
                        // row: a line that appears moves everything above it.
                        Text(
                            state.plan?.let { plan ->
                                "${formatShutter(plan.exposureNs)} · ISO ${plan.iso} · " +
                                    plan.outcome.name.lowercase()
                            } ?: "auto exposure",
                            color = Color(0x99FFFFFF),
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier
                                .padding(start = 8.dp, top = 2.dp, bottom = 2.dp)
                                .testTag("capture-exposure-plan"),
                        )
                    }
                }
                TextButton(
                    onClick = { showShutterMenu = !showShutterMenu },
                    modifier = Modifier
                        .background(LightGlass, RoundedCornerShape(20.dp))
                        .testTag("shutter-speed-button"),
                ) {
                    Text("⚡ " + exposureLabel(state.exposureRule, state.plan), color = Color.White)
                }
            }

            // The original's CaptureQueueIndicator: the in-flight save and
            // the session's running total, in a dark pill. There is no
            // multi-item capture queue in this port (CameraX hands the
            // JPEG straight to the storage chain), so the 💾 slot only
            // shows while a save is in flight.
            val sessionTotal = CaptureSessionCounters.totalCaptured.value
            if (state.capturing || sessionTotal > 0 || queueStats.refining > 0) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    modifier = Modifier
                        .background(DarkGlass, RoundedCornerShape(20.dp))
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                        .testTag("capture-queue-indicator"),
                ) {
                    if (state.capturing) {
                        Text("💾 …", color = Color.White, style = MaterialTheme.typography.bodySmall)
                    }
                    // Stamp refinements in flight — the "anything's in
                    // flight" twinkle the refiner design promised. Their
                    // photos wait out the interpolation before uploading.
                    if (queueStats.refining > 0) {
                        Text(
                            "⟳${queueStats.refining}",
                            color = Color.White,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.testTag("refine-indicator"),
                        )
                    }
                    if (sessionTotal > 0) {
                        Text(
                            "($sessionTotal)",
                            color = Color.White,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }

        // The catch zone, drawn as what it IS: the gesture accepts any point
        // left of the button (pos.x < circle.left) — the ladder is not a
        // thin track to aim at. Nothing said so, and precision-aiming at a
        // line was the real reason arming kept being missed (user-caught:
        // "i kept trying to target the track exactly").
        //
        // Since the zone is the hit-box, the zone is now also the SCALE: the
        // rungs are its bands, at the size the finger actually selects them,
        // over the pane's full height. That is one rect for the picture and
        // the gesture both, where the old rotated slider drew one scale
        // beside the button and read another.
        val circle = circleBounds
        if (ladderVisible && circle != null) {
            val zoneWidth = with(androidx.compose.ui.platform.LocalDensity.current) {
                (circle.left - paneOrigin.x).coerceAtLeast(0f).toDp()
            }
            IntervalLadder(
                hoverIndex = hoverIndex,
                armed = armedIndex != null,
                pointerFraction = pointerFraction,
                modifier = Modifier
                    .align(Alignment.CenterStart)
                    .fillMaxHeight()
                    .width(zoneWidth),
            )
        }

        // Bottom-centre stack over the video: hints and gate escapes above
        // the shutter, as the original stacks its absolute elements above
        // shutter-container (bottom: 6px, centred).
        Column(
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            // Appears exactly when calibration would help: walking-mode
            // bearing with the magnetometer reporting below-HIGH accuracy.
            // Red and above the shutter, as the original places it.
            if (needsCompassCalibration(
                    walkingMode = mapSettings.bearingMode == cz.hillview.map.BearingMode.Walking,
                    accuracyLevel = state.compassAccuracy,
                )
            ) {
                Button(
                    onClick = { showCalibration = true },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE24A4A)),
                    modifier = Modifier.testTag("calibrate-compass-btn"),
                ) { Text("Calibrate Compass") }
            }

            if (manualClaimed) {
                GlassAction(
                    text = "Capturing at map position" +
                        (capture.manualLocation?.let {
                            " (${fmt(it.latitude)}, ${fmt(it.longitude)})"
                        } ?: "") +
                        " — tap for GPS",
                    tag = "capture-manual-override",
                ) {
                    // Withdrawing the claim from here: back to the fix.
                    session.setLocationTracking(cz.hillview.map.LocationTracking.Active)
                }
            }

            // The gate's escape hatch: shooting underground means positioning
            // the map by hand first and capturing against that.
            //
            // The OFFER is only made while the gate is actually shut, but the
            // resulting state stays on screen for as long as it is in effect —
            // including after a fix arrives. It used to vanish with the fix
            // while still being the elected position, so the label's promise
            // ("tap to require GPS again") had no button to tap, and a
            // coordinate marked hours ago could come back silently.
            if (state.ready && !manualClaimed) {
                if (mapPositionWithoutFix) {
                    GlassAction(
                        text = "Using map position" +
                            (capture.manualLocation?.let {
                                " (${fmt(it.latitude)}, ${fmt(it.longitude)})"
                            } ?: "") +
                            " — tap to require GPS again",
                        tag = "capture-manual-location",
                    ) {
                        session.setMapPositionWithoutFix(false)
                    }
                } else if (!state.hasFix) {
                    GlassAction(
                        text = "No GPS fix — capture at the map position instead",
                        tag = "capture-use-map-position",
                    ) {
                        session.setMapPositionWithoutFix(true)
                    }
                }
            }

            // A recording says so, out loud and on-pane. It used to say
            // nothing at all (user-caught: "video recording isn't indicated
            // in any way?") — the button that stops it looked exactly like
            // the button that starts a photo, and the only difference a
            // running recording made was invisible.
            state.recordingStartedAtMs?.takeIf { state.recording }?.let { startedAt ->
                RecordingIndicator(startedAtMs = startedAt)
            }

            // The shutter, shaped like the original's DualCaptureButton —
            // and driven like it, as ONE gesture. Tap = one shot. Holding
            // 300 ms (the original's "shorter timeout for quicker
            // response") unfolds the interval ladder over the pane beside
            // the still-held thumb; sliding onto it picks a rung live;
            // RELEASING there starts the repeating run. Releasing back over
            // the button cancels, as the original's release-over-nothing
            // does. A tap stops a running run. The graded ladder is this
            // port's take on the original's fixed slow/fast pair.
            var clusterOrigin by remember { mutableStateOf(Offset.Zero) }
            val gateOpen =
                shutterEnabled(state.ready, state.hasFix, manualElected)
            // The location gate (see shutterEnabled): no fix, no photo —
            // unless deliberately lifted (the local lift OR the pill's
            // accepted claim; phone-in-hand find: the claim used to leave
            // the gate shut).
            val tappable = shutterPressDoesSomething(
                recording = state.recording,
                repeating = repeating,
                gateOpen = gateOpen,
                capturing = state.capturing,
            )
            Box(
                Modifier
                    .onGloballyPositioned { clusterOrigin = it.positionInRoot() }
                    // state.recording is a KEY, not just read inside: the
                    // gesture lambda captures the state it was created with,
                    // and pointerInput only restarts when a key changes — so
                    // without this the handler kept a pre-recording snapshot
                    // and a tap could never stop a recording (device-caught).
                    .pointerInput(gateOpen, repeating, state.recording) {
                        // The camera is CALLED from inside this block
                        // (capture(), startVideo(), the Sports engagement's
                        // request-options write). An exception escaping
                        // awaitEachGesture kills this pointerInput coroutine,
                        // and it only comes back when a KEY changes — after
                        // a run ends, none does. That is a shutter dead
                        // until the app restarts, which is what the field
                        // reported. So: one gesture may fail; the handler
                        // may not.
                        awaitEachGesture {
                          try {
                            val down = awaitFirstDown(requireUnconsumed = false)
                            val circle = circleBounds ?: run {
                                ignoredPress = "shutter not laid out yet"
                                return@awaitEachGesture
                            }
                            if (!circle.contains(clusterOrigin + down.position)) {
                                return@awaitEachGesture
                            }
                            // STOPPING comes before the gate, deliberately.
                            // The location gate exists to withhold a capture
                            // that would have no position; it has no business
                            // withholding the end of one. It used to run
                            // first, so a fix lost mid-recording left the
                            // recording unstoppable — every press answered
                            // "no GPS fix" — and the same trap held a
                            // repeating run.
                            if (state.recording) {
                                // Recording behaves exactly like a run: any
                                // completed press on the button ends it.
                                val up = waitForUpOrCancellation() ?: return@awaitEachGesture
                                if (circle.contains(clusterOrigin + up.position)) {
                                    capture.stopVideo()
                                }
                                return@awaitEachGesture
                            }
                            if (repeating) {
                                // A running run: any completed press on the
                                // button stops it (the original's
                                // handleSingleCapture with activeMode set).
                                val up = waitForUpOrCancellation() ?: return@awaitEachGesture
                                if (circle.contains(clusterOrigin + up.position)) repeating = false
                                return@awaitEachGesture
                            }
                            if (!gateOpen) {
                                ignoredPress = if (!state.ready) "camera not ready" else "no GPS fix"
                                return@awaitEachGesture
                            }
                            if (state.capturing) {
                                ignoredPress = "previous shot still in flight"
                                return@awaitEachGesture
                            }
                            down.consume()
                            val quick = withTimeoutOrNull(300L) {
                                if (waitForUpOrCancellation() != null) "tap" else "cancel"
                            }
                            if (quick == "tap") {
                                capture.capture()
                                return@awaitEachGesture
                            }
                            if (quick == "cancel") return@awaitEachGesture
                            // Long-press reached with the finger still down.
                            // Seed the ladder from where the finger already
                            // IS, so it opens showing the truth rather than
                            // the last run's rung — the thumb is on the
                            // button at the foot of the scale, and that is
                            // what the bottom band should say.
                            paneBounds?.let { zone ->
                                val y = (clusterOrigin + down.position).y
                                hoverIndex = rungIndexAt(y, zone.top, zone.bottom)
                                pointerFraction = ladderFractionAt(y, zone.top, zone.bottom)
                            }
                            ladderVisible = true
                            var overLadder = false
                            try {
                                while (true) {
                                    val event = awaitPointerEvent()
                                    val change = event.changes.firstOrNull { it.id == down.id }
                                        ?: event.changes.first()
                                    val pos = clusterOrigin + change.position
                                    // Everything left of the button is the
                                    // ladder's catch zone — a mid-gesture
                                    // thumb is not a precision instrument.
                                    overLadder = pos.x < circle.left
                                    // The ladder spans the pane, so the pane
                                    // is the scale. Height is read whatever
                                    // the finger's x is: the ladder shows
                                    // where the gesture is landing even
                                    // while the thumb is still on the
                                    // button, so the target is visible
                                    // BEFORE the slide left commits to it.
                                    val zone = paneBounds
                                    if (zone != null && zone.height > 0f) {
                                        hoverIndex = rungIndexAt(pos.y, zone.top, zone.bottom)
                                        pointerFraction =
                                            ladderFractionAt(pos.y, zone.top, zone.bottom)
                                        if (overLadder) intervalIndex = hoverIndex
                                    }
                                    armedIndex = if (overLadder) intervalIndex else null
                                    change.consume()
                                    if (event.changes.none { it.pressed }) {
                                        // Released on the ladder: the top
                                        // rung starts a recording, any
                                        // interval rung starts a run.
                                        val rung = INTERVAL_LADDER.getOrNull(intervalIndex)
                                        if (overLadder && rung is LadderRung.Video) {
                                            videoEngaged = engageSportsIfAuto()
                                            capture.startVideo()
                                        } else if (overLadder && rung is LadderRung.Every) {
                                            repeating = true
                                        }
                                        break
                                    }
                                }
                            } finally {
                                // The ladder lives exactly as long as the
                                // finger does, run or no run.
                                ladderVisible = false
                                armedIndex = null
                                pointerFraction = null
                            }
                          } catch (e: kotlinx.coroutines.CancellationException) {
                            throw e
                          } catch (e: Exception) {
                            // Logged where the user can see it; the next
                            // press gets a live handler either way.
                            ladderVisible = false
                            armedIndex = null
                            pointerFraction = null
                            ignoredPress = "shutter error: ${e.message ?: e::class.simpleName}"
                          }
                        }
                    },
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .background(DarkGlass, RoundedCornerShape(40.dp))
                        .padding(4.dp),
                ) {
                    // No slider beside the button any more: the ladder IS
                    // the catch zone (see IntervalLadder), so the cluster
                    // keeps its size when the gesture unfolds — it used to
                    // grow to the slider's 280 dp and carry the button ~115
                    // dp up the pane, out from under the finger holding it.
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        modifier = Modifier
                            .size(70.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    // Recording outranks the gate: this is
                                    // the STOP button now, and a fix lost
                                    // mid-recording must not disguise it.
                                    state.recording -> Color(0xFFD32F2F)
                                    !gateOpen -> Color(0x802196F3)
                                    repeating -> Color(0xFF4CAF50)
                                    // Armed: wear the colour NOW that the
                                    // release is about to make true — the
                                    // run's green, video's red. The button
                                    // previews its own future instead of
                                    // leaving it to a label off to the side.
                                    armedRung is LadderRung.Video -> Color(0xFFD32F2F)
                                    armedRung is LadderRung.Every -> Color(0xFF4CAF50)
                                    else -> Color(0xFF2196F3)
                                },
                            )
                            .onGloballyPositioned { circleBounds = it.boundsInRoot() }
                            // Touch goes through the cluster's pointerInput
                            // (the gesture spans ladder and button); this
                            // keeps the click/enabled contract for tests
                            // and accessibility.
                            .semantics {
                                role = Role.Button
                                if (!tappable) disabled()
                                onClick(label = null) {
                                    if (!tappable) return@onClick false
                                    when {
                                        state.recording -> capture.stopVideo()
                                        repeating -> repeating = false
                                        else -> capture.capture()
                                    }
                                    true
                                }
                            }
                            .testTag("capture-shutter"),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                when {
                                    state.recording -> "⏺"
                                    armedRung is LadderRung.Video -> "⏺"
                                    armedRung is LadderRung.Every -> "▶"
                                    state.capturing && !repeating -> "…"
                                    else -> "📷"
                                },
                                style = MaterialTheme.typography.titleMedium,
                            )
                            when {
                                state.recording -> Text(
                                    "Stop",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White,
                                )
                                armedRung is LadderRung.Video -> Text(
                                    "REC",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White,
                                )
                                armedRung is LadderRung.Every -> Text(
                                    armedRung.label,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White,
                                )
                                repeating -> Text(
                                    "Stop",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White,
                                )
                            }
                        }
                    }
                    // The release verdict, spelled out while the ladder is
                    // open: what letting go does, right under the button
                    // that is previewing it. This is the line the old
                    // ladder head could not carry (clipped off-pane at
                    // common splits — the original cause of "i keep missing
                    // it"); the ladder itself now names the rung too, in
                    // the band it is highlighting.
                    if (ladderVisible) {
                        Text(
                            text = when {
                                armedRung is LadderRung.Video -> "release: record"
                                armedRung is LadderRung.Every ->
                                    "release: start ${armedRung.label} run"
                                // The bottom rung and the button itself are
                                // the same act, so they get the same word.
                                else -> "release: cancel"
                            },
                            style = MaterialTheme.typography.labelSmall,
                            color = when {
                                armedRung is LadderRung.Video -> Color(0xFFFF5252)
                                armedRung is LadderRung.Every -> Color(0xFF69F0AE)
                                else -> Color(0xB3FFFFFF)
                            },
                            modifier = Modifier
                                .padding(top = 2.dp)
                                .testTag("capture-armed-hint"),
                        )
                    }
                    }
                }
                // The original's capture-counter badge, live during a run.
                if (runCount > 0) {
                    Text(
                        "$runCount",
                        color = Color.White,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .background(Color(0xFF2196F3), RoundedCornerShape(10.dp))
                            .padding(horizontal = 6.dp, vertical = 1.dp)
                            .testTag("capture-run-count"),
                    )
                }
            }
        }

        // Drawn last: the card floats over whatever the top-left stack
        // shows, as the original's absolute overlay does.
        if (promptVisible) {
            AutoUploadPrompt(
                onConfigure = { promptVisible = false; onOpenSettings() },
                onDismiss = { promptVisible = false; promptDismissed = true },
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(start = 16.dp, top = 110.dp),
            )
        }
    }

    if (showCalibration) {
        CompassCalibrationOverlay(
            accuracyLevel = state.compassAccuracy,
            walkingMode = mapSettings.bearingMode == cz.hillview.map.BearingMode.Walking,
            onSwitchToCarMode = {
                mapSettingsRepo.update { it.copy(bearingMode = cz.hillview.map.BearingMode.Car) }
            },
            onClose = { showCalibration = false },
        )
    }
}

/**
 * The Leaf's fps ladder, unfolding beneath it mid-gesture. A display like
 * [IntervalLadder]: the Leaf's pointerInput drives [t] (0 = bottom =
 * capture-only, 1 = top = default) from the held thumb via the reported
 * track bounds.
 */
@Composable
private fun EcoSlider(
    t: Float,
    onTrackPositioned: (Rect) -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .background(DarkGlass, RoundedCornerShape(24.dp))
            .padding(6.dp),
    ) {
        Text(
            text = ecoFpsLabel(ecoSliderToFps(t)),
            style = MaterialTheme.typography.bodySmall,
            color = Color.White,
            modifier = Modifier.testTag("eco-fps-value"),
        )
        Box(
            modifier = Modifier
                .size(width = 48.dp, height = 140.dp)
                .onGloballyPositioned { onTrackPositioned(it.boundsInRoot()) },
            contentAlignment = Alignment.Center,
        ) {
            Slider(
                value = t,
                onValueChange = {},
                valueRange = 0f..1f,
                modifier = Modifier
                    .requiredWidth(140.dp)
                    .rotate(-90f)
                    .testTag("eco-fps-slider"),
            )
        }
    }
}

/**
 * The camera-lifecycle line, rendered as a pill row. No fix state here:
 * the pill's own rows carry it (📍 when a fix exists, the spinner when
 * not) — "GPS fix"/"no GPS fix" used to repeat that in words. No bearing
 * either: the 🧭 row shows it live. What remains is what the pill can't
 * say: the camera's own state, the last save, and errors (⚠️-prefixed —
 * one type style up here, no red exception).
 */
internal fun statusLineText(state: CaptureState): String = buildList {
    add(
        when {
            !state.supported -> "⚠️ " + (state.errorMessage ?: "Not supported on this platform")
            !state.ready -> "Starting camera…"
            else -> "ready"
        }
    )
    state.lastPhoto?.let { photo ->
        val s = photo.snapshot
        val loc = if (s.latitude != null && s.longitude != null) {
            "@${fmt(s.latitude)},${fmt(s.longitude)}"
        } else {
            "no location"
        }
        add("saved ${photo.filename} $loc")
    }
    state.errorMessage?.takeIf { state.supported }?.let { add("⚠️ $it") }
}.joinToString(" · ")

private fun fmt(value: Double): String {
    val rounded = (value * 100_000).roundToInt() / 100_000.0
    return rounded.toString()
}

/**
 * "● REC 0:12" while a recording runs, blinking once a second.
 *
 * The blink and the clock come off ONE ticker, so the dot and the seconds
 * cannot disagree about how long this has been going. The dot fades rather
 * than disappearing — a glyph that comes and goes shifts the text beside it
 * twice a second, which reads as a fault rather than a heartbeat.
 *
 * The dot-and-elapsed shape is the app's own, from the clock-video recorder
 * in both apps ("● Recording — 12s"); the period is the original's
 * `blink 1s step-start`.
 *
 * Its own composable so the ticker's recomposition stops here, rather than
 * redrawing the pane and its camera preview twice a second.
 */
@Composable
internal fun RecordingIndicator(startedAtMs: Long) {
    var now by remember(startedAtMs) { mutableStateOf(nowMs()) }
    LaunchedEffect(startedAtMs) {
        while (true) {
            now = nowMs()
            delay(RECORDING_BLINK_MS)
        }
    }
    val elapsed = (now - startedAtMs).coerceAtLeast(0L)
    val lit = (elapsed / RECORDING_BLINK_MS) % 2 == 0L
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .background(DarkGlass, RoundedCornerShape(20.dp))
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .testTag("capture-recording"),
    ) {
        Text(
            "●",
            color = Color(0xFFFF5252).copy(alpha = if (lit) 1f else 0f),
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(end = 6.dp),
        )
        Text(
            "REC ${formatElapsed(elapsed)}",
            color = Color.White,
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

/** The original's `blink 1s step-start`: half a second lit, half dark. */
private const val RECORDING_BLINK_MS = 500L

/**
 * A control readable over live video: dark glass backing, light text —
 * the treatment every original overlay button gets from its CSS.
 */
@Composable
private fun GlassAction(text: String, tag: String, onClick: () -> Unit) {
    TextButton(
        onClick = onClick,
        modifier = Modifier
            .background(DarkGlass, RoundedCornerShape(20.dp))
            .testTag(tag),
    ) { Text(text, color = Color.White) }
}

/** The dim section heading the 📷 and ⚡ menus divide their rows with. */
@Composable
private fun MenuLabel(text: String) {
    Text(
        text,
        color = Color(0x99FFFFFF),
        style = MaterialTheme.typography.labelSmall,
        modifier = Modifier.padding(start = 8.dp, top = 4.dp),
    )
}

/** A test tag that survives being a decimal: -0.5 → "m5", +1.0 → "p10". */
private fun evTag(ev: Double): String {
    val tenths = (ev * 10).roundToInt()
    return if (tenths < 0) "m${-tenths}" else "p$tenths"
}

// Compact on purpose: Material's default button min-width would push the
// fast end of the ladder offscreen, and an invisible chip is an untappable
// one.
@Composable
private fun ShutterChip(label: String, selected: Boolean, tag: String, onClick: () -> Unit) {
    TextButton(
        onClick = onClick,
        enabled = !selected,
        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 4.dp),
        modifier = Modifier
            .defaultMinSize(minWidth = 1.dp, minHeight = 32.dp)
            .testTag(tag),
    ) { Text(if (selected) "[$label]" else label, color = Color.White) }
}

/**
 * "Your photos are staying on this device." The original
 * (AutoUploadPrompt.svelte) is a floating card OVER the video — absolute,
 * top-left, dark — never a dialog: one red configure button (the path to
 * upload settings, where the licence gate lives) and an × dismiss. Its
 * neverAskAgain() exists but no button renders it — mirrored here; the
 * settings screen owns that switch (auto_upload_prompt_enabled).
 */
@Composable
private fun AutoUploadPrompt(
    onConfigure: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .background(Color(0xF21E1E1E), RoundedCornerShape(8.dp))
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .testTag("auto-upload-prompt"),
    ) {
        Button(
            onClick = onConfigure,
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFD32F2F)),
            modifier = Modifier.testTag("configure-auto-upload"),
        ) { Text("⚙️ Configure auto-upload", color = Color.White) }
        Box(
            modifier = Modifier
                .padding(start = 8.dp)
                .size(24.dp)
                .clip(CircleShape)
                .background(Color(0x1AFFFFFF))
                .clickable(onClick = onDismiss)
                .testTag("dismiss-auto-upload-prompt"),
            contentAlignment = Alignment.Center,
        ) { Text("×", color = Color(0xFFAAAAAA)) }
    }
}

@Composable
private fun ResolutionOption(
    label: String,
    selected: Boolean,
    tag: String,
    onClick: () -> Unit,
) {
    TextButton(
        onClick = onClick,
        modifier = Modifier.testTag(tag),
    ) {
        Text(
            if (selected) "[$label]" else label,
            color = if (selected) {
                Color(0xFF4A90E2)
            } else {
                Color.White
            },
            style = MaterialTheme.typography.bodySmall,
        )
    }
}


/**
 * The original's `bearing-tracking-hint`: shown in the capture pane while
 * neither bearing source is on, dismissible for good. Without it the frozen
 * heading reads as a bug rather than as a switch nobody flipped.
 */
@Composable
private fun BearingTrackingHint(onEnable: () -> Unit, onDismiss: () -> Unit) {
    androidx.compose.material3.Surface(
        color = androidx.compose.material3.MaterialTheme.colorScheme.surfaceVariant,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
        modifier = Modifier.padding(4.dp).testTag("bearing-tracking-hint"),
    ) {
        androidx.compose.foundation.layout.Row(
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
            modifier = Modifier.padding(horizontal = 8.dp),
        ) {
            androidx.compose.material3.Text(
                "Turn on bearing tracking?",
                style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
            )
            androidx.compose.material3.TextButton(
                onClick = onEnable,
                modifier = Modifier.testTag("enable-bearing-hint"),
            ) { androidx.compose.material3.Text("🧭") }
            androidx.compose.material3.TextButton(
                onClick = onDismiss,
                modifier = Modifier.testTag("dismiss-bearing-hint"),
            ) { androidx.compose.material3.Text("✕") }
        }
    }
}
