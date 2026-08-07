package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.requiredWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Slider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import cz.hillview.upload.PendingUpload
import cz.hillview.upload.UploadPipeline
import kotlinx.coroutines.delay
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

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

    // 0 = one shot per tap; otherwise the shutter arms a repeating run.
    var intervalSec by rememberSaveable { mutableStateOf(0) }
    var repeating by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(repeating, intervalSec) {
        if (!repeating || intervalSec <= 0) return@LaunchedEffect
        while (true) {
            if (!state.capturing) capture.capture()
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

    // A pane of the Main page now (no header, no back — the floating camera
    // button toggles the activity): the preview takes what the controls
    // leave, and the controls scroll when the pane runs short.
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f),
        ) {
            capture.CameraPane(Modifier.fillMaxSize())


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
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(start = 24.dp, top = 24.dp),
            )
            // The 📷 selector, lower-left as in Tauri. Only resolutions for
            // now; the camera rows join when enumeration is ported.
            if (state.availableResolutions.isNotEmpty()) {
                Column(Modifier.align(Alignment.BottomStart).padding(8.dp)) {
                    if (showResolutionMenu) {
                        Column(
                            Modifier
                                .background(
                                    androidx.compose.ui.graphics.Color(0xDD222222),
                                    androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
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
        }

        Column(
            modifier = Modifier
                .weight(1f, fill = false)
                .verticalScroll(androidx.compose.foundation.rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {

        if (promptVisible) {
            AutoUploadPrompt(
                onConfigure = { promptVisible = false; onOpenSettings() },
                onDismiss = { promptVisible = false; promptDismissed = true },
                onNever = {
                    promptVisible = false
                    uploadSettingsRepo.update { it.copy(autoUploadPromptEnabled = false) }
                },
            )
        }

        StatusLine(state)

        Text(
            text = "uploads: ${queueStats.done} done" +
                (if (queueStats.duplicate > 0) ", ${queueStats.duplicate} dup" else "") +
                (if (queueStats.pending > 0) ", ${queueStats.pending} pending" else "") +
                (if (queueStats.failed > 0) ", ${queueStats.failed} failed" else "") +
                (queueStats.lastError?.let { " · $it" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("capture-upload-stats"),
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // The Leaf: lower preview fps here, and the map only catches up
            // after each capture instead of chasing every fix.
            TextButton(
                onClick = {
                    mapSettingsRepo.update { it.copy(powerSavingPref = !it.powerSavingPref) }
                },
                modifier = Modifier.testTag("power-saving-btn"),
            ) {
                Text(
                    if (ecoActive) "[eco]" else "eco",
                    color = if (ecoActive) {
                        androidx.compose.ui.graphics.Color(0xFF2EA043)
                    } else {
                        androidx.compose.ui.graphics.Color.Gray
                    },
                )
            }

            // Appears exactly when calibration would help: walking-mode
            // bearing with the magnetometer reporting below-HIGH accuracy.
            if (needsCompassCalibration(
                    walkingMode = mapSettings.bearingMode == cz.hillview.map.BearingMode.Walking,
                    accuracyLevel = state.compassAccuracy,
                )
            ) {
                TextButton(
                    onClick = { showCalibration = true },
                    modifier = Modifier.testTag("calibrate-compass-btn"),
                ) { Text("Calibrate Compass") }
            }
        }

        // Shutter time, for crisp shots out of a moving vehicle. Only shown
        // where the sensor takes manual orders at all; ISO follows the pin
        // automatically (shutter priority), so this stays a one-axis
        // control.
        if (state.manualShutterSupported) {
            @OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
            androidx.compose.foundation.layout.FlowRow(
                // Wraps: the ladder overflows a narrow phone, and an
                // offscreen chip is an untappable one — scrolling just
                // hides the problem, a second line does not.
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text("Shutter", style = MaterialTheme.typography.bodySmall)
                val active = state.shutterNs

                // Compact on purpose: Material's default button min-width
                // would push the fast end of the ladder offscreen, and an
                // invisible chip is an untappable one.
                @Composable
                fun chip(label: String, selected: Boolean, tag: String, onClick: () -> Unit) {
                    TextButton(
                        onClick = onClick,
                        enabled = !selected,
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            horizontal = 6.dp, vertical = 4.dp,
                        ),
                        modifier = Modifier
                            .defaultMinSize(minWidth = 1.dp, minHeight = 32.dp)
                            .testTag(tag),
                    ) { Text(if (selected) "[$label]" else label) }
                }

                chip("Auto", active == null, "capture-shutter-auto") {
                    capture.shutterNs = null
                }
                SHUTTER_CHOICES_NS.forEach { ns ->
                    chip(
                        formatShutter(ns),
                        active == ns,
                        "capture-shutter-${1_000_000_000L / ns}",
                    ) { capture.shutterNs = ns }
                }
            }
        }

        if (manualClaimed) {
            TextButton(
                onClick = {
                    // Withdrawing the claim from here: back to the fix.
                    session.setLocationTracking(cz.hillview.map.LocationTracking.Active)
                },
                modifier = Modifier.testTag("capture-manual-override"),
            ) {
                val at = capture.manualLocation
                Text(
                    "Capturing at map position" +
                        (at?.let { " (${fmt(it.latitude)}, ${fmt(it.longitude)})" } ?: "") +
                        " — tap for GPS",
                )
            }
        }

        // The gate's escape hatch, offered only while it is actually shut:
        // shooting underground means positioning the map by hand first and
        // capturing against that.
        if (state.ready && !state.hasFix) {
            if (!manualLocationArmed) {
                TextButton(
                    onClick = {
                        val spatial = mapState.spatial.value
                        capture.manualLocation = ManualLocation(
                            latitude = spatial.latitude,
                            longitude = spatial.longitude,
                        )
                        manualLocationArmed = true
                    },
                    modifier = Modifier.testTag("capture-use-map-position"),
                ) {
                    Text("No GPS fix — capture at the map position instead")
                }
            } else {
                TextButton(
                    onClick = {
                        capture.manualLocation = null
                        manualLocationArmed = false
                    },
                    modifier = Modifier.testTag("capture-manual-location"),
                ) {
                    val at = capture.manualLocation
                    Text(
                        "Using map position" +
                            (at?.let { " (${fmt(it.latitude)}, ${fmt(it.longitude)})" } ?: "") +
                            " — tap to require GPS again",
                    )
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Interval as a continuous slider rather than a couple of fixed
            // modes: the useful spacing depends on how fast you're moving.
            IntervalSlider(
                intervalSec = intervalSec,
                enabled = !repeating,
                onChange = { intervalSec = it },
            )

            Button(
                onClick = {
                    if (intervalSec == 0) capture.capture() else repeating = !repeating
                },
                // The location gate (see shutterEnabled): no fix, no photo —
                // unless the user has deliberately lifted it below.
                enabled = shutterEnabled(state.ready, state.hasFix, manualLocationArmed) &&
                    (repeating || !state.capturing),
                modifier = Modifier
                    .size(width = 160.dp, height = 56.dp)
                    .testTag("capture-shutter"),
            ) {
                Text(
                    when {
                        repeating -> "Stop"
                        intervalSec > 0 -> "Start ${intervalSec}s"
                        state.capturing -> "…"
                        else -> "Capture"
                    }
                )
            }
        }
        } // controls scroll column
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
            MaterialTheme.colorScheme.onSurface
        },
        modifier = Modifier
            .fillMaxWidth()
            .testTag("capture-status"),
    )
}

private fun fmt(value: Double): String {
    val rounded = (value * 100_000).roundToInt() / 100_000.0
    return rounded.toString()
}

/**
 * "Your photos are staying on this device." One line, three exits — the
 * same three the original offers: configure (goes to upload settings, where
 * the licence gate lives), not now, and never (persisted, so the overlay
 * can never block a rapid-fire run again).
 */
@Composable
private fun AutoUploadPrompt(
    onConfigure: () -> Unit,
    onDismiss: () -> Unit,
    onNever: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .testTag("auto-upload-prompt"),
    ) {
        Text(
            "Auto-upload is off — captures stay on this device.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Row {
            TextButton(
                onClick = onConfigure,
                modifier = Modifier.testTag("configure-auto-upload"),
            ) { Text("Set up") }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testTag("dismiss-auto-upload-prompt"),
            ) { Text("Not now") }
            TextButton(
                onClick = onNever,
                modifier = Modifier.testTag("never-auto-upload-prompt"),
            ) { Text("Never ask") }
        }
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
                androidx.compose.ui.graphics.Color(0xFF4A90E2)
            } else {
                androidx.compose.ui.graphics.Color.White
            },
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
