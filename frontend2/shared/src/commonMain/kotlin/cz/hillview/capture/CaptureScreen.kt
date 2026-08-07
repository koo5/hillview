package cz.hillview.capture

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.ui.graphics.Color
import cz.hillview.upload.PendingUpload
import cz.hillview.upload.UploadPipeline
import kotlinx.coroutines.delay
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@OptIn(ExperimentalFoundationApi::class)
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

    // The lifted-gate state: session-scoped, so the fix requirement guards
    // every fresh visit and lifting it is a deliberate act each time.
    var manualLocationArmed by rememberSaveable { mutableStateOf(false) }
    // The LIVE map state — the same holder the always-mounted map pane
    // renders, so follow-me and the claim move the camera the user is
    // looking at (a store write would go behind the mounted map's back).
    val mapState: cz.hillview.map.MapStateHolder = org.koin.compose.koinInject()
    val mapSettingsRepo: cz.hillview.settings.MapSettingsRepository = org.koin.compose.koinInject()
    val mapSettings by mapSettingsRepo.settings.collectAsState()
    val session: cz.hillview.map.MapSession = org.koin.compose.koinInject()
    val locationTracking by session.locationTracking.collectAsState()
    val manualClaimed by session.manualPositionClaimed.collectAsState()

    // A claimed manual position (accepted on the map) overrides the fix:
    // captures geotag from the map centre, tagged "manual" — and the
    // degraded shutter tone says so out loud.
    LaunchedEffect(manualClaimed) {
        if (manualClaimed) {
            val spatial = mapState.spatial.value
            capture.manualLocation = ManualLocation(spatial.latitude, spatial.longitude)
            capture.manualLocationWins = true
        } else {
            capture.manualLocationWins = false
            if (!manualLocationArmed) capture.manualLocation = null
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
    // the activity gate the Tauri `powerSavingActive` derives.
    val ecoActive = mapSettings.powerSavingPref
    LaunchedEffect(ecoActive) { capture.ecoPreviewFps = ecoActive }

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

    // 0 = one shot per tap; otherwise the shutter arms a repeating run.
    var intervalSec by rememberSaveable { mutableStateOf(0) }
    var repeating by rememberSaveable { mutableStateOf(false) }
    // The slider hides until a long press on the shutter summons it — the
    // original's 300 ms press expands its slow/fast modes the same way —
    // then folds away after a few untouched seconds.
    var intervalVisible by remember { mutableStateOf(false) }
    var sliderTouched by remember { mutableStateOf(0) }
    var runCount by remember { mutableStateOf(0) }
    LaunchedEffect(intervalVisible, sliderTouched, repeating) {
        if (intervalVisible) {
            delay(5_000)
            intervalVisible = false
        }
    }

    LaunchedEffect(repeating, intervalSec) {
        if (!repeating || intervalSec <= 0) {
            // The original zeroes its badge when the run stops.
            runCount = 0
            return@LaunchedEffect
        }
        while (true) {
            if (!state.capturing) {
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
            )
        )
        // Under eco the map catches up here, once per capture — Tauri's
        // "power saving: map catches up after each capture".
        if (locationTracking == cz.hillview.map.LocationTracking.Active &&
            photo.snapshot.locationSource == "gps" &&
            photo.snapshot.latitude != null && photo.snapshot.longitude != null
        ) {
            followMapTo(photo.snapshot.latitude, photo.snapshot.longitude)
        }

        // The original waits 800 ms after the shutter before prompting, "to
        // avoid UI confusion" right at the moment of capture.
        if (!uploadSettings.autoUploadEnabled &&
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

        // Top-left stack at the original pill's spot (CameraOverlay.svelte:
        // top 60px / left 60px — clear of Main's floating hamburger row).
        // The status and upload lines are this port's extension; they ride
        // under the pill as glass strips instead of claiming pane rows.
        Column(
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(start = 60.dp, top = 56.dp, end = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            horizontalAlignment = Alignment.Start,
        ) {
            CameraOverlayUi(
                state = state,
                bearingMode = mapSettings.bearingMode,
                overridePosition = if (capture.manualLocationWins) capture.manualLocation else null,
                opacityLevel = mapSettings.cameraOverlayOpacity,
                onCycleOpacity = {
                    mapSettingsRepo.update {
                        it.copy(cameraOverlayOpacity = nextOverlayOpacity(it.cameraOverlayOpacity))
                    }
                },
            )
            StatusLine(state)
            Text(
                text = "uploads: ${queueStats.done} done" +
                    (if (queueStats.duplicate > 0) ", ${queueStats.duplicate} dup" else "") +
                    (if (queueStats.pending > 0) ", ${queueStats.pending} pending" else "") +
                    (if (queueStats.failed > 0) ", ${queueStats.failed} failed" else "") +
                    (queueStats.lastError?.let { " · $it" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = Color(0x99FFFFFF),
                modifier = Modifier
                    .background(Color(0x66000000), RoundedCornerShape(4.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp)
                    .testTag("capture-upload-stats"),
            )
        }

        // The Leaf — the original's power-saving-button: a translucent
        // circle below the top-right corner (that corner belongs to the
        // debug toggles there). Lower preview fps, and the map only catches
        // up after each capture instead of chasing every fix.
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(top = 52.dp, end = 8.dp)
                .size(38.dp)
                .clip(CircleShape)
                .background(if (ecoActive) Color(0xCC2EA043) else Color(0x33FFFFFF))
                .clickable {
                    mapSettingsRepo.update { it.copy(powerSavingPref = !it.powerSavingPref) }
                }
                .testTag("power-saving-btn"),
            contentAlignment = Alignment.Center,
        ) { Text("🍃") }

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
                    }
                }
                TextButton(
                    onClick = { showResolutionMenu = !showResolutionMenu },
                    modifier = Modifier.testTag("camera-selector-button"),
                ) { Text("📷", style = MaterialTheme.typography.titleMedium) }
            }
        }

        // Shutter time, for crisp shots out of a moving vehicle — this
        // port's addition (the original has no manual exposure). Collapsed
        // behind a ⚡ button in the lower-right, expanding upward like the
        // camera selector; the open ladder used to sprawl across the pane
        // (round-4 feedback). ISO follows the pin automatically (shutter
        // priority), so this stays a one-axis control.
        if (state.manualShutterSupported) {
            Column(
                Modifier.align(Alignment.BottomEnd).padding(end = 8.dp, bottom = 6.dp),
                horizontalAlignment = Alignment.End,
            ) {
                if (showShutterMenu) {
                    Column(
                        Modifier
                            .background(Color(0xDD222222), RoundedCornerShape(8.dp))
                            .padding(4.dp)
                            .testTag("shutter-speed-menu"),
                    ) {
                        ShutterChip("Auto", state.shutterNs == null, "capture-shutter-auto") {
                            showShutterMenu = false
                            capture.shutterNs = null
                        }
                        SHUTTER_CHOICES_NS.forEach { ns ->
                            ShutterChip(
                                formatShutter(ns),
                                state.shutterNs == ns,
                                "capture-shutter-${1_000_000_000L / ns}",
                            ) {
                                showShutterMenu = false
                                capture.shutterNs = ns
                            }
                        }
                    }
                }
                TextButton(
                    onClick = { showShutterMenu = !showShutterMenu },
                    modifier = Modifier.testTag("shutter-speed-button"),
                ) {
                    Text(
                        "⚡ " + (state.shutterNs?.let { formatShutter(it) } ?: "Auto"),
                        color = Color.White,
                    )
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

            // The gate's escape hatch, offered only while it is actually
            // shut: shooting underground means positioning the map by hand
            // first and capturing against that.
            if (state.ready && !state.hasFix && !manualClaimed) {
                if (!manualLocationArmed) {
                    GlassAction(
                        text = "No GPS fix — capture at the map position instead",
                        tag = "capture-use-map-position",
                    ) {
                        val spatial = mapState.spatial.value
                        capture.manualLocation = ManualLocation(
                            latitude = spatial.latitude,
                            longitude = spatial.longitude,
                        )
                        manualLocationArmed = true
                    }
                } else {
                    GlassAction(
                        text = "Using map position" +
                            (capture.manualLocation?.let {
                                " (${fmt(it.latitude)}, ${fmt(it.longitude)})"
                            } ?: "") +
                            " — tap to require GPS again",
                        tag = "capture-manual-location",
                    ) {
                        capture.manualLocation = null
                        manualLocationArmed = false
                    }
                }
            }

            // The shutter, shaped like the original's DualCaptureButton: a
            // dark pill holding a circular button. A plain tap is one shot;
            // a long press reveals the interval slider (this port's
            // continuous take on the original's slow/fast pair); with an
            // interval armed, a tap starts/stops the repeating run.
            Box {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .background(Color(0x80000000), RoundedCornerShape(40.dp))
                        .padding(4.dp),
                ) {
                    if (intervalVisible) {
                        IntervalSlider(
                            intervalSec = intervalSec,
                            enabled = !repeating,
                            onChange = { intervalSec = it; sliderTouched++ },
                        )
                    }

                    val gateOpen =
                        shutterEnabled(state.ready, state.hasFix, manualLocationArmed || manualClaimed)
                    Box(
                        modifier = Modifier
                            .size(70.dp)
                            .clip(CircleShape)
                            .background(
                                when {
                                    // The location gate (see shutterEnabled):
                                    // no fix, no photo — unless deliberately
                                    // lifted (the local lift OR the pill's
                                    // accepted claim; phone-in-hand find: the
                                    // claim used to leave the gate shut).
                                    !gateOpen -> Color(0x802196F3)
                                    repeating -> Color(0xFF4CAF50)
                                    else -> Color(0xFF2196F3)
                                },
                            )
                            .combinedClickable(
                                enabled = gateOpen && (repeating || !state.capturing),
                                onLongClick = { intervalVisible = true; sliderTouched++ },
                                onClick = {
                                    if (intervalSec == 0) capture.capture() else repeating = !repeating
                                },
                            )
                            .testTag("capture-shutter"),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                if (state.capturing && !repeating) "…" else "📷",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            val label = when {
                                repeating -> "Stop"
                                intervalSec > 0 -> "${intervalSec}s"
                                else -> null
                            }
                            label?.let {
                                Text(
                                    it,
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

/** Off, then 1…60 s. Vertical because it sits beside the shutter. */
@Composable
private fun IntervalSlider(
    intervalSec: Int,
    enabled: Boolean,
    onChange: (Int) -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.padding(end = 16.dp),
    ) {
        Text(
            text = if (intervalSec == 0) "single" else "${intervalSec}s",
            style = MaterialTheme.typography.bodySmall,
            color = Color.White,
            modifier = Modifier.testTag("capture-interval-value"),
        )
        Box(
            modifier = Modifier.size(width = 48.dp, height = 140.dp),
            contentAlignment = Alignment.Center,
        ) {
            // Material has no vertical slider; rotating a horizontal one and
            // giving it the box's height as its width is the usual trick.
            Slider(
                value = intervalSec.toFloat(),
                onValueChange = { onChange(it.roundToInt()) },
                valueRange = 0f..60f,
                enabled = enabled,
                modifier = Modifier
                    .requiredWidth(140.dp)
                    .rotate(-90f)
                    .testTag("capture-interval-slider"),
            )
        }
    }
}

@Composable
private fun StatusLine(state: CaptureState) {
    val parts = buildList {
        add(
            when {
                !state.supported -> state.errorMessage ?: "Not supported on this platform"
                !state.ready -> "Starting camera…"
                state.hasFix -> "GPS fix"
                else -> "no GPS fix"
            }
        )
        state.bearingDeg?.let { add("bearing ${it.roundToInt()}°") }
        state.lastPhoto?.let { photo ->
            val s = photo.snapshot
            val loc = if (s.latitude != null && s.longitude != null) {
                "@${fmt(s.latitude)},${fmt(s.longitude)}"
            } else {
                "no location"
            }
            add("saved ${photo.filename} $loc")
        }
        state.errorMessage?.takeIf { state.supported }?.let { add(it) }
    }
    Text(
        text = parts.joinToString(" · "),
        style = MaterialTheme.typography.bodySmall,
        color = if (state.errorMessage != null && state.supported) {
            MaterialTheme.colorScheme.error
        } else {
            // Light on the glass strip, over live video.
            Color(0xCCFFFFFF)
        },
        modifier = Modifier
            .background(Color(0x66000000), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
            .testTag("capture-status"),
    )
}

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
            .background(Color(0xAA000000), RoundedCornerShape(20.dp))
            .testTag(tag),
    ) { Text(text, color = Color.White) }
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
