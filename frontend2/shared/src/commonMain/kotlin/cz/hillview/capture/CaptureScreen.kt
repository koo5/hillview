package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import kotlin.math.roundToInt

// The two glass families every original overlay uses: dark pills for info
// and actions (rgba(0,0,0,.5–.7) in the CSS), white glass for the utility
// buttons (rgba(255,255,255,.2)). One constant each — the pane had drifted
// into five different alphas of black (phone-in-hand feedback: unify).
// The location pill is NOT in either family: its six-level white cycle is
// the ported CameraOverlay contract.
internal val DarkGlass = Color(0xB3000000)
internal val LightGlass = Color(0x33FFFFFF)

// Same physical track, finer grain: 15 s is the longest useful spacing
// (the original's slow mode is 10 s) — a 60 s ceiling made every useful
// value crowd the bottom centimetre of the slider.
internal const val INTERVAL_MAX_SEC = 15

/**
 * One stop above the fastest interval: VIDEO. Video is a modality of this
 * pane — "almost just a 0-interval photo capture" — so it is chosen the
 * same way a run is: hold the shutter, slide up the ladder, release. Past
 * the top of the seconds is where "even less than zero interval" belongs.
 */
internal const val LADDER_VIDEO_STOP = INTERVAL_MAX_SEC + 1

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
    // The stamp position is the map's centre, LIVE — same shape as the stamp
    // bearing below, and the same as Tauri, whose locationData is reactive on
    // $spatialState. It was previously read once at the electing moment, so
    // claiming at one place, panning to another and shooting stamped the
    // first while the tracking table recorded the second: the photo and the
    // log disagreed about where the user said they were. Always populated;
    // manualLocationElected alone decides whether anything reads it.
    LaunchedEffect(Unit) {
        mapState.spatial.collect { s ->
            capture.manualLocation = ManualLocation(s.latitude, s.longitude)
        }
    }
    // The capture stamp bearing IS the map's bearing state (Tauri:
    // locationData.bearing = bearingState.bearing): car mode's
    // gps-kalman + mount offset, walking's compass, or the hand-set
    // arrow — whichever currently owns the arrow.
    LaunchedEffect(Unit) {
        mapState.bearing.collect { b ->
            capture.stampBearing = StampBearing(b.bearing.toFloat(), b.source)
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

    // The last-used interval doubles as the slider's starting position when
    // the gesture next unfolds it; repeating is the running-run flag.
    var intervalSec by rememberSaveable { mutableStateOf(0) }
    var repeating by rememberSaveable { mutableStateOf(false) }
    var runCount by remember { mutableStateOf(0) }

    // The ⚡ menu edits a target and a bias whether or not a rule is in
    // force, so switching back off Auto returns to what was last set up
    // rather than to a default. 1/500 is the middle of the ladder.
    var exposureTargetNs by rememberSaveable { mutableStateOf(2_000_000L) }
    var exposureBias by rememberSaveable { mutableStateOf(0.0) }

    LaunchedEffect(repeating, intervalSec) {
        if (!repeating || intervalSec <= 0) {
            // The original zeroes its badge when the run stops.
            runCount = 0
            return@LaunchedEffect
        }
        while (true) {
            if (!state.capturing) {
                // Hand AE the camera back for a moment first: an exposure
                // rule turns it off, and without this the whole run would
                // be exposed for whatever the scene was when the rule was
                // chosen. This is the one place we own the clock, so it is
                // the one place it can be done — no-op under Auto.
                capture.prepareExposure()
                capture.capture()
                runCount++
            }
            delay(intervalSec * 1000L)
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

    // The capture pane IS the camera stream — the original's camera-content
    // fills with the video and positions every control absolutely over it
    // (CameraCapture.svelte styles). No control rows under the video, no
    // scroll column. (Round-4 phone-in-hand feedback: the previous cut kept
    // a letterboxed preview above a stack of visible controls.)
    Box(
        modifier = Modifier
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
            CameraOverlayUi(
                state = state,
                bearingMode = mapSettings.bearingMode,
                overridePosition = if (capture.manualLocationElected) capture.manualLocation else null,
                opacityLevel = mapSettings.cameraOverlayOpacity,
                onCycleOpacity = {
                    mapSettingsRepo.update {
                        it.copy(cameraOverlayOpacity = nextOverlayOpacity(it.cameraOverlayOpacity))
                    }
                },
                statusText = statusLineText(state),
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

                        // The bias biases the METERING, so it needs a rule
                        // of ours to ride on — under auto exposure the
                        // camera's own AE owns that decision.
                        state.exposureRule?.let { rule ->
                            MenuLabel("Bias")
                            Row {
                                EV_BIAS_CHOICES.forEach { ev ->
                                    ShutterChip(
                                        formatEvBias(ev),
                                        rule.evBias == ev,
                                        "capture-exposure-ev-${evTag(ev)}",
                                    ) {
                                        exposureBias = ev
                                        capture.exposureRule = rule.copy(evBias = ev)
                                    }
                                }
                            }
                        }

                        // What the rule actually resolved to last time it
                        // was applied — the only honest answer to "is this
                        // mode working here?", live, in the field.
                        state.plan?.let { plan ->
                            Text(
                                "${formatShutter(plan.exposureNs)} · ISO ${plan.iso} · " +
                                    plan.outcome.name.lowercase(),
                                color = Color(0x99FFFFFF),
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier
                                    .padding(start = 8.dp, top = 2.dp, bottom = 2.dp)
                                    .testTag("capture-exposure-plan"),
                            )
                        }
                    }
                }
                TextButton(
                    onClick = { showShutterMenu = !showShutterMenu },
                    modifier = Modifier
                        .background(LightGlass, RoundedCornerShape(20.dp))
                        .testTag("shutter-speed-button"),
                ) {
                    Text("⚡ " + exposureLabel(state.exposureRule), color = Color.White)
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

            // The shutter, shaped like the original's DualCaptureButton —
            // and driven like it, as ONE gesture. Tap = one shot. Holding
            // 300 ms (the original's "shorter timeout for quicker
            // response") unfolds the interval slider beside the still-held
            // thumb; sliding onto it picks an interval live; RELEASING
            // there starts the repeating run. Releasing back over the
            // button cancels, as the original's release-over-nothing does.
            // A tap stops a running run. The continuous slider is this
            // port's take on the original's fixed slow/fast pair.
            var sliderVisible by remember { mutableStateOf(false) }
            var circleBounds by remember { mutableStateOf<Rect?>(null) }
            var sliderZone by remember { mutableStateOf<Rect?>(null) }
            var clusterOrigin by remember { mutableStateOf(Offset.Zero) }
            val gateOpen =
                shutterEnabled(state.ready, state.hasFix, manualElected)
            // The location gate (see shutterEnabled): no fix, no photo —
            // unless deliberately lifted (the local lift OR the pill's
            // accepted claim; phone-in-hand find: the claim used to leave
            // the gate shut).
            val tappable = gateOpen && (repeating || !state.capturing)
            Box(
                Modifier
                    .onGloballyPositioned { clusterOrigin = it.positionInRoot() }
                    // state.recording is a KEY, not just read inside: the
                    // gesture lambda captures the state it was created with,
                    // and pointerInput only restarts when a key changes — so
                    // without this the handler kept a pre-recording snapshot
                    // and a tap could never stop a recording (device-caught).
                    .pointerInput(gateOpen, repeating, state.recording) {
                        awaitEachGesture {
                            val down = awaitFirstDown(requireUnconsumed = false)
                            val circle = circleBounds ?: return@awaitEachGesture
                            if (!circle.contains(clusterOrigin + down.position)) {
                                return@awaitEachGesture
                            }
                            if (!gateOpen) return@awaitEachGesture
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
                            if (state.capturing) return@awaitEachGesture
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
                            sliderVisible = true
                            var overSlider = false
                            try {
                                while (true) {
                                    val event = awaitPointerEvent()
                                    val change = event.changes.firstOrNull { it.id == down.id }
                                        ?: event.changes.first()
                                    val pos = clusterOrigin + change.position
                                    // Everything left of the button is the
                                    // slider's catch zone — a mid-gesture
                                    // thumb is not a precision instrument.
                                    overSlider = pos.x < circle.left
                                    val zone = sliderZone
                                    if (overSlider && zone != null && zone.height > 0f) {
                                        intervalSec =
                                            ((zone.bottom - pos.y) / zone.height * LADDER_VIDEO_STOP)
                                                .roundToInt().coerceIn(0, LADDER_VIDEO_STOP)
                                    }
                                    change.consume()
                                    if (event.changes.none { it.pressed }) {
                                        // Released on the ladder: the top
                                        // stop starts a recording, anything
                                        // above "single" starts a run.
                                        if (overSlider && intervalSec == LADDER_VIDEO_STOP) {
                                            capture.startVideo()
                                        } else if (overSlider && intervalSec > 0) {
                                            repeating = true
                                        }
                                        break
                                    }
                                }
                            } finally {
                                // The slider lives exactly as long as the
                                // finger does, run or no run.
                                sliderVisible = false
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
                    if (sliderVisible) {
                        IntervalSlider(
                            intervalSec = intervalSec,
                            enabled = true,
                            onChange = { intervalSec = it },
                            onTrackPositioned = { sliderZone = it },
                        )
                    }

                    Box(
                        modifier = Modifier
                            .size(70.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    !gateOpen -> Color(0x802196F3)
                                    repeating -> Color(0xFF4CAF50)
                                    else -> Color(0xFF2196F3)
                                },
                            )
                            .onGloballyPositioned { circleBounds = it.boundsInRoot() }
                            // Touch goes through the cluster's pointerInput
                            // (the gesture spans slider and button); this
                            // keeps the click/enabled contract for tests
                            // and accessibility.
                            .semantics {
                                role = Role.Button
                                if (!tappable) disabled()
                                onClick(label = null) {
                                    if (!tappable) return@onClick false
                                    if (repeating) repeating = false else capture.capture()
                                    true
                                }
                            }
                            .testTag("capture-shutter"),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                if (state.capturing && !repeating) "…" else "📷",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            if (repeating) {
                                Text(
                                    "Stop",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color.White,
                                )
                            }
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
 * [IntervalSlider]: the Leaf's pointerInput drives [t] (0 = bottom =
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
 * Off, then 1…[INTERVAL_MAX_SEC] s. Vertical because it sits beside the
 * shutter. During the one-finger gesture it is a display — the cluster's
 * pointerInput drives the value from the thumb position via
 * [onTrackPositioned]'s reported track bounds (root coords, bottom = 0 s,
 * top = the max).
 */
/**
 * The ladder's length. Doubled from 140 dp (user-raised: "the scale is a
 * bit hard to use") — 16 stops over 140 dp is ~9 dp each, well under a
 * comfortable thumb increment, and this control is driven by a thumb
 * sliding along it rather than by tapping a knob.
 *
 * ONE constant because the rotated-slider trick needs the box's height and
 * the slider's required width to be the same number; two literals that must
 * agree is a bug waiting for whoever changes one.
 */
private val INTERVAL_TRACK_LENGTH = 280.dp

@Composable
private fun IntervalSlider(
    intervalSec: Int,
    enabled: Boolean,
    onChange: (Int) -> Unit,
    onTrackPositioned: (Rect) -> Unit = {},
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.padding(end = 16.dp),
    ) {
        Text(
            text = when (intervalSec) {
                0 -> "single"
                LADDER_VIDEO_STOP -> "VIDEO"
                else -> "${intervalSec}s"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (intervalSec == LADDER_VIDEO_STOP) Color(0xFFFF5252) else Color.White,
            modifier = Modifier.testTag("capture-interval-value"),
        )
        Box(
            modifier = Modifier
                .size(width = 48.dp, height = INTERVAL_TRACK_LENGTH)
                .onGloballyPositioned { onTrackPositioned(it.boundsInRoot()) },
            contentAlignment = Alignment.Center,
        ) {
            // Material has no vertical slider; rotating a horizontal one and
            // giving it the box's height as its width is the usual trick.
            Slider(
                value = intervalSec.toFloat(),
                onValueChange = { onChange(it.roundToInt()) },
                valueRange = 0f..LADDER_VIDEO_STOP.toFloat(),
                enabled = enabled,
                modifier = Modifier
                    .requiredWidth(INTERVAL_TRACK_LENGTH)
                    .rotate(-90f)
                    .testTag("capture-interval-slider"),
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
