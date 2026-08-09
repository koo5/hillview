package cz.hillview.main

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.auth.SessionManager
import cz.hillview.auth.SessionState
import cz.hillview.capture.CaptureScreen
import cz.hillview.core.nowMs
import cz.hillview.map.MapScreen
import cz.hillview.map.MapSession
import cz.hillview.map.MapStateHolder
import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * The Main page — the app itself, as the Tauri `/` route is (see
 * docs/tauri-map-ui-contract.md, "Main page: routes, activities, split
 * layout"): a resizable split with the photo panel over an ALWAYS-mounted
 * map. Activities (view | capture) switch panel content, never navigation;
 * the activity and the split are persisted. Real navigation exists only
 * behind the hamburger (settings, login, clock video).
 *
 * Lines and terrain are web-only activities — not ported.
 */
@Composable
fun MainScreen(
    onOpenSettings: () -> Unit,
    onOpenLogin: () -> Unit,
    onOpenClockVideo: () -> Unit,
    onOpenDevicePhotos: () -> Unit,
    onOpenCaptureGuide: () -> Unit = {},
    settingsRepo: MapSettingsRepository = koinInject(),
    session: MapSession = koinInject(),
    sessionManager: SessionManager = koinInject(),
    stateHolder: MapStateHolder = koinInject(),
) {
    val mapSettings by settingsRepo.settings.collectAsState()
    val activity = mapSettings.mainActivity
    val sessionState by sessionManager.state.collectAsState()
    val expiredNotice by sessionManager.sessionExpiredNotice.collectAsState()
    val scope = rememberCoroutineScope()
    var menuOpen by remember { mutableStateOf(false) }
    var showStats by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { sessionManager.restoreIfNeeded() }

    // The ONE place that decides when position/heading hardware runs, and
    // with what. The activity drives WHEN; the values are supplied here, so
    // a GPS-interval slider becomes an argument rather than a re-plumbing.
    // (Until that setting exists, the default cadence both apps have always
    // used.) Panes below are pure observers of the resulting streams.
    val bearingWanted by session.bearingTrackingWanted.collectAsState()
    val locationTracking by session.locationTracking.collectAsState()
    cz.hillview.geo.BindGeoToActivity(
        activity = activity,
        mapWantsTracking = bearingWanted ||
            locationTracking != cz.hillview.map.LocationTracking.Off,
        gpsIntervalMs = 1_000L,
    )

    // The original's appOldActivity block: entering capture arms tracking
    // (both on a toggle AND on initial load of a persisted capture
    // activity); returning to view stands the bearing side down.
    var oldActivity by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(activity) {
        if (oldActivity != activity) {
            when {
                activity == "capture" -> session.onEnterCapture()
                oldActivity == "capture" -> session.onLeaveCapture()
            }
            oldActivity = activity
        }
    }

    fun toggleCamera() {
        val entering = activity != "capture"
        if (entering && stateHolder.spatial.value.zoom < 17.0) {
            // The original bumps a wide view to street level on entering
            // capture — that is where the photo is about to be taken.
            stateHolder.updateSpatial(zoom = 17.0, now = nowMs())
        }
        settingsRepo.update {
            it.copy(mainActivity = if (entering) "capture" else "view")
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()) {
        val portrait = maxHeight >= maxWidth
        val totalPx = if (portrait) constraints.maxHeight else constraints.maxWidth
        var split by remember { mutableStateOf(mapSettings.splitPercent.coerceIn(10f, 90f)) }

        val photoPanel: @Composable () -> Unit = {
            when (activity) {
                "capture" -> CaptureScreen(onOpenSettings = onOpenSettings)
                // The external-camera mode: a peer of capture in the same
                // panel slot (no camera stream; a foreground service keeps
                // the record alive while the system camera owns the screen).
                "external" -> cz.hillview.external.ExternalCameraPane()
                else -> GalleryPlaceholder()
            }
        }
        val mapPanel: @Composable () -> Unit = {
            MapScreen(
                settings = settingsRepo,
                markerSource = koinInject(),
                stateHolder = stateHolder,
                stateStore = koinInject(),
                session = session,
            )
        }
        val divider: @Composable () -> Unit = {
            // The split ruler: a visible grip, so the drag affordance reads
            // at a glance (the original's resizableSplit bar).
            Box(
                modifier = Modifier
                    .then(
                        if (portrait) {
                            Modifier.fillMaxWidth().height(14.dp)
                        } else {
                            Modifier.fillMaxHeight().width(14.dp)
                        },
                    )
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .testTag("split-divider")
                    .pointerInput(portrait, totalPx) {
                        detectDragGestures(
                            onDrag = { change, dragAmount ->
                                change.consume()
                                val delta = if (portrait) dragAmount.y else dragAmount.x
                                split = (split + delta / totalPx * 100f).coerceIn(10f, 90f)
                            },
                            onDragEnd = {
                                settingsRepo.update { it.copy(splitPercent = split) }
                            },
                        )
                    },
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    Modifier
                        .then(
                            if (portrait) {
                                Modifier.width(48.dp).height(5.dp)
                            } else {
                                Modifier.height(48.dp).width(5.dp)
                            },
                        )
                        .background(
                            MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                            RoundedCornerShape(3.dp),
                        ),
                )
            }
        }

        // clipToBounds on both panes: Compose's view-interop containers do
        // not clip children, so osmdroid's tile pass would draw full tiles
        // past the pane edge, overreaching into the photo panel.
        if (portrait) {
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxWidth().weight(split).clipToBounds()) { photoPanel() }
                divider()
                Box(Modifier.fillMaxWidth().weight(100f - split).clipToBounds()) { mapPanel() }
            }
        } else {
            Row(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxHeight().weight(split).clipToBounds()) { photoPanel() }
                divider()
                Box(Modifier.fillMaxHeight().weight(100f - split).clipToBounds()) { mapPanel() }
            }
        }

        // Floating controls along the top-left, as the original places them
        // (hamburger at the edge, camera next to it).
        Row(Modifier.align(Alignment.TopStart).padding(4.dp)) {
            FloatingControl(
                label = "☰",
                tag = "hamburger-menu",
                onClick = { menuOpen = !menuOpen },
            )
            FloatingControl(
                label = "📷",
                tag = "camera-button",
                active = activity == "capture",
                onClick = {
                    menuOpen = false
                    toggleCamera()
                },
            )
        }

        // The involuntary-death notice, persistent until addressed — the
        // original keeps it in the main page's alert area.
        expiredNotice?.let { reason ->
            Text(
                text = "Your session has expired ($reason) — please sign in again.",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 56.dp, start = 16.dp, end = 16.dp)
                    .background(
                        MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
                        RoundedCornerShape(6.dp),
                    )
                    .clickable {
                        scope.launch { sessionManager.dismissSessionExpiredNotice() }
                    }
                    .padding(8.dp)
                    .testTag("session-expired-notice"),
            )
        }

        if (menuOpen) {
            // Scrim: any outside tap closes.
            Box(
                Modifier
                    .fillMaxSize()
                    .clickable { menuOpen = false },
            )
            Surface(
                tonalElevation = 6.dp,
                shape = RoundedCornerShape(bottomEnd = 12.dp),
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(top = 52.dp)
                    .testTag("navigation-menu"),
            ) {
                Column(Modifier.padding(8.dp)) {
                    Text(
                        text = when (val s = sessionState) {
                            is SessionState.LoggedIn -> "Signed in as ${s.username ?: "?"}"
                            SessionState.LoggedOut -> "Not signed in"
                            SessionState.Unknown -> "…"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier
                            .padding(horizontal = 12.dp, vertical = 4.dp)
                            .testTag("menu-session-status"),
                    )
                    MenuLink("Settings", "settings-menu-link") {
                        menuOpen = false
                        onOpenSettings()
                    }
                    MenuLink("Device photos", "menu-device-photos") {
                        menuOpen = false
                        onOpenDevicePhotos()
                    }
                    MenuLink("Stats", "menu-capture-stats") {
                        menuOpen = false
                        showStats = true
                    }
                    MenuLink("Capture guide", "menu-capture-guide") {
                        menuOpen = false
                        onOpenCaptureGuide()
                    }
                    MenuLink("External camera", "menu-external-camera") {
                        menuOpen = false
                        settingsRepo.update { it.copy(mainActivity = "external") }
                    }
                    MenuLink("Clock video", "menu-clock-video") {
                        menuOpen = false
                        onOpenClockVideo()
                    }
                    if (sessionState is SessionState.LoggedIn) {
                        MenuLink("Sign out", "menu-logout-button") {
                            menuOpen = false
                            scope.launch { sessionManager.logout() }
                        }
                    } else {
                        MenuLink("Sign in", "menu-login-button") {
                            menuOpen = false
                            onOpenLogin()
                        }
                    }
                }
            }
        }
    }

        // The copyable performance numbers (user-requested): live while
        // open, monospace, selectable — plus one-tap Copy for pasting
        // into a chat or a bug note.
        if (showStats) {
            var statsText by remember { mutableStateOf("") }
            LaunchedEffect(Unit) {
                while (true) {
                    statsText = cz.hillview.capture.CaptureStatsLog
                        .snapshotText(cz.hillview.core.nowMs())
                    kotlinx.coroutines.delay(1_000)
                }
            }
            val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
            androidx.compose.material3.AlertDialog(
                onDismissRequest = { showStats = false },
                confirmButton = {
                    cz.hillview.core.ui.InstantDialogWindow()
                    TextButton(
                        onClick = {
                            clipboard.setText(
                                androidx.compose.ui.text.AnnotatedString(statsText),
                            )
                        },
                        modifier = Modifier.testTag("stats-copy-button"),
                    ) { Text("Copy") }
                    TextButton(
                        onClick = { cz.hillview.capture.CaptureStatsLog.reset() },
                    ) { Text("Reset") }
                    TextButton(onClick = { showStats = false }) { Text("Close") }
                },
                title = { Text("Capture stats") },
                text = {
                    androidx.compose.foundation.text.selection.SelectionContainer {
                        Text(
                            statsText.ifEmpty { "No captures yet." },
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.testTag("stats-text"),
                        )
                    }
                },
            )
        }
}

@Composable
private fun FloatingControl(
    label: String,
    tag: String,
    active: Boolean = false,
    onClick: () -> Unit,
) {
    Surface(
        shape = CircleShape,
        tonalElevation = 4.dp,
        color = if (active) {
            MaterialTheme.colorScheme.primaryContainer
        } else {
            MaterialTheme.colorScheme.surface
        },
        modifier = Modifier.padding(4.dp),
    ) {
        TextButton(onClick = onClick, modifier = Modifier.testTag(tag)) {
            Text(label, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun MenuLink(label: String, tag: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth().testTag(tag)) {
        Text(label, modifier = Modifier.fillMaxWidth())
    }
}

/**
 * The view activity's photo panel. The real gallery (photo display, swipe
 * between in-range photos) is its own future piece — deliberately not
 * sketched here, per the plan.
 */
@Composable
private fun GalleryPlaceholder() {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .testTag("gallery-placeholder"),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            "Photo gallery — on its way",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
