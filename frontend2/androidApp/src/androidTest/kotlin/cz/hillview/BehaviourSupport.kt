package cz.hillview

import android.content.Context
import android.location.Location
import android.location.LocationManager
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.test.ComposeTimeoutException
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.platform.app.InstrumentationRegistry
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoEntity
import cz.hillview.plugin.SimplePhotoDao
import java.net.HttpURLConnection
import java.net.URL

/**
 * Shared plumbing for the Appium behaviour ports — the scenario sources are
 * frontend/tests-appium/specs/, the assertions docs/app-behaviour-scenarios.md.
 */
object Behaviour {
    val context: Context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    /** The shared-kt Room DB — the same rows the Tauri suites read through cmd.get_device_photos. */
    fun photoDao(): SimplePhotoDao = PhotoDatabase.getDatabase(context).photoDao()

    fun shell(command: String): String {
        val pfd = InstrumentationRegistry.getInstrumentation()
            .uiAutomation.executeShellCommand(command)
        return ParcelFileDescriptor.AutoCloseInputStream(pfd)
            .use { String(it.readBytes()) }
    }

    /**
     * POST to the dev backend's debug surface (10.0.2.2 = host loopback).
     * Returns the HTTP status, or -1 when unreachable — callers Assume on
     * it so backend-needing tests SKIP rather than fail when it is down.
     */
    /** Where dumpAndClear writes the geo CSVs — same directory in both apps. */
    fun geoDumpDir(): java.io.File =
        java.io.File(context.getExternalFilesDir(null), "GeoTrackingDumps")

    /** The newest dump of a kind ("locations" | "orientations"), or null. */
    fun newestGeoDump(kind: String): java.io.File? =
        geoDumpDir().listFiles { f -> f.name.startsWith("hillview_${kind}_") }
            ?.maxByOrNull { it.lastModified() }

    /**
     * A dump read by HEADER NAME. The dumps have gained columns twice (detail,
     * elected), so reading a column by position is a future false failure —
     * this is the Kotlin twin of csvColumn() in the appium spec.
     */
    fun geoDumpRows(file: java.io.File): List<Map<String, String>> {
        val lines = file.readLines().filter { it.isNotBlank() }
        if (lines.isEmpty()) return emptyList()
        val header = splitCsv(lines.first().removePrefix("#"))
        return lines.drop(1).map { line -> header.zip(splitCsv(line)).toMap() }
    }

    /** Field splitter honouring the quoting escapeCsv() writes. */
    private fun splitCsv(line: String): List<String> {
        val out = mutableListOf<String>()
        val cell = StringBuilder()
        var quoted = false
        var i = 0
        while (i < line.length) {
            val c = line[i]
            when {
                quoted && c == '"' && i + 1 < line.length && line[i + 1] == '"' -> {
                    cell.append('"'); i++
                }
                c == '"' -> quoted = !quoted
                c == ',' && !quoted -> {
                    out.add(cell.toString()); cell.clear()
                }
                else -> cell.append(c)
            }
            i++
        }
        out.add(cell.toString())
        return out
    }

    fun post(url: String, jsonBody: String? = null): Int = try {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.connectTimeout = 5_000
        conn.readTimeout = 20_000
        if (jsonBody != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(jsonBody.toByteArray()) }
        }
        try {
            conn.responseCode
        } finally {
            conn.disconnect()
        }
    } catch (e: Exception) {
        -1
    }
}

/**
 * A mock GPS provider. While installed it REPLACES the emulator's virtual
 * GPS, which is what makes the location gate deterministic: no fix arrives
 * unless the test [inject]s one — the Appium suites got the same control
 * from the emulator console's `geo fix`, which instrumentation cannot reach.
 */
class MockGps {
    private val locationManager =
        Behaviour.context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private val fused =
        com.google.android.gms.location.LocationServices
            .getFusedLocationProviderClient(Behaviour.context)

    /** Call before the capture screen opens, so its GPS subscribe sees the mock. */
    @Suppress("DEPRECATION")
    fun install() {
        // The shell grant is what "select mock location app" toggles in
        // developer options; without it addTestProvider throws.
        Behaviour.shell(
            "appops set ${Behaviour.context.packageName} android:mock_location allow",
        )
        locationManager.addTestProvider(
            LocationManager.GPS_PROVIDER,
            /* requiresNetwork = */ false,
            /* requiresSatellite = */ true,
            /* requiresCell = */ false,
            /* hasMonetaryCost = */ false,
            /* supportsAltitude = */ true,
            /* supportsSpeed = */ true,
            /* supportsBearing = */ true,
            android.location.Criteria.POWER_HIGH,
            android.location.Criteria.ACCURACY_FINE,
        )
        locationManager.setTestProviderEnabled(LocationManager.GPS_PROVIDER, true)
        // Belt and braces: the fused provider keeps a SYSTEM-wide cache
        // (it survives reinstalls) and can surface a past fix even while
        // the platform GPS provider is mocked silent. Its own mock mode
        // makes it forget the world until we say otherwise.
        com.google.android.gms.tasks.Tasks.await(fused.setMockMode(true))
    }

    fun inject(latitude: Double, longitude: Double) {
        val location = Location(LocationManager.GPS_PROVIDER).apply {
            this.latitude = latitude
            this.longitude = longitude
            accuracy = 5f
            altitude = 300.0
            // Both stamps are required or the platform rejects the fix;
            // elapsedRealtimeNanos is also what hasFix freshness reads.
            time = System.currentTimeMillis()
            elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
        }
        locationManager.setTestProviderLocation(LocationManager.GPS_PROVIDER, location)
        com.google.android.gms.tasks.Tasks.await(fused.setMockLocation(location))
    }

    fun remove() {
        try {
            com.google.android.gms.tasks.Tasks.await(fused.setMockMode(false))
        } catch (_: Exception) {
            // mock mode never engaged
        }
        try {
            locationManager.removeTestProvider(LocationManager.GPS_PROVIDER)
        } catch (_: Exception) {
            // install() failed before adding the provider — nothing to undo
        }
    }
}

// --- capture-screen drives ---

/** The capture-status line's text, or "" while the screen isn't up. */
fun ComposeTestRule.captureStatus(): String {
    val node = onAllNodesWithTag("capture-status").fetchSemanticsNodes().firstOrNull()
        ?: return ""
    return node.config.getOrNull(SemanticsProperties.Text)
        ?.joinToString(" ") { it.text } ?: ""
}

fun ComposeTestRule.shutterIsEnabled(): Boolean {
    val node = onAllNodesWithTag("capture-shutter").fetchSemanticsNodes().firstOrNull()
        ?: return false
    return !node.config.contains(SemanticsProperties.Disabled)
}

/**
 * Switch the Main page into the capture activity, then wait out the camera
 * cold start on the capped emulator.
 *
 * The activity is PERSISTED: a previous test may have left it on, in which
 * case the capture pane composed at activity launch — BEFORE this test's
 * setup (mock GPS install, prefs) ran. Bounce it so the camera pane
 * re-subscribes under the test's arrangements.
 */
fun ComposeTestRule.openCaptureAndAwaitCamera() {
    if (onAllNodesWithTag("capture-status").fetchSemanticsNodes().isNotEmpty()) {
        onNodeWithTag("camera-button").performClick()
        waitUntil(10_000) {
            onAllNodesWithTag("capture-status").fetchSemanticsNodes().isEmpty()
        }
    }
    onNodeWithTag("camera-button").performClick()
    waitUntil(15_000) {
        onAllNodesWithTag("capture-status").fetchSemanticsNodes().isNotEmpty()
    }
    waitUntil(45_000) {
        val status = captureStatus()
        status.isNotEmpty() && !status.contains("Starting camera")
    }
}

/**
 * Open the shutter by WHATEVER stands: a live fix, a standing claim, or —
 * failing both — the manual lift. For tests that need capture to work and
 * don't assert the gate's semantics (that's CaptureGatingBehaviourTest's
 * job, which uses the strict [liftGateToMapPosition]).
 */
fun ComposeTestRule.ensureCaptureReady() {
    waitUntil(15_000) {
        shutterIsEnabled() ||
            onAllNodesWithTag("capture-use-map-position").fetchSemanticsNodes().isNotEmpty()
    }
    if (!shutterIsEnabled()) {
        runCatching { onNodeWithTag("capture-use-map-position").performScrollTo() }
        onNodeWithTag("capture-use-map-position").performClick()
        waitUntil(5_000) { shutterIsEnabled() }
    }
}

/** The item-13 escape hatch: no fix → capture at the map position instead. */
fun ComposeTestRule.liftGateToMapPosition() {
    waitUntil(10_000) {
        onAllNodesWithTag("capture-use-map-position").fetchSemanticsNodes().isNotEmpty()
    }
    // The capture pane's controls scroll now that it shares the screen
    // with the map — bring the target into view before tapping.
    runCatching { onNodeWithTag("capture-use-map-position").performScrollTo() }
    onNodeWithTag("capture-use-map-position").performClick()
    waitUntil(5_000) { shutterIsEnabled() }
}

/**
 * One shutter press, waited through the whole pipeline: JPEG → storage
 * chain → shared-kt Room row. Returns the row that landed.
 */
fun ComposeTestRule.captureOnePhoto(): PhotoEntity {
    val dao = Behaviour.photoDao()
    val before = dao.getTotalPhotoCount()
    waitUntil(15_000) { shutterIsEnabled() }
    runCatching { onNodeWithTag("capture-shutter").performScrollTo() }
    onNodeWithTag("capture-shutter").performClick()
    waitUntil(30_000) { dao.getTotalPhotoCount() > before }
    return dao.getAllPhotos().maxByOrNull { it.createdAt }!!
}

/**
 * Put a Switch into the wanted state, wherever in the scrollable settings
 * column it sits. Clicking blindly would TOGGLE — reading the toggleable
 * state first makes this idempotent, which is what lets tests arrange
 * state without caring what previous tests (or previous runs — app data
 * persists on the emulator) left behind.
 */
fun ComposeTestRule.setSwitch(tag: String, on: Boolean) {
    val wanted = if (on) ToggleableState.On else ToggleableState.Off
    val node = onNodeWithTag(tag).performScrollTo()
    if (node.fetchSemanticsNode().config[SemanticsProperties.ToggleableState] != wanted) {
        node.performClick()
    }
    waitUntil(3_000) {
        onNodeWithTag(tag).fetchSemanticsNode()
            .config[SemanticsProperties.ToggleableState] == wanted
    }
}

/** Open the Main page's hamburger menu; no-op when already open. */
fun ComposeTestRule.openMenu() {
    if (onAllNodesWithTag("navigation-menu").fetchSemanticsNodes().isNotEmpty()) return
    onNodeWithTag("hamburger-menu").performClick()
    waitUntil(5_000) {
        onAllNodesWithTag("navigation-menu").fetchSemanticsNodes().isNotEmpty()
    }
}

/** Close the menu via its scrim (the click-outside path). */
fun ComposeTestRule.closeMenu() {
    if (onAllNodesWithTag("navigation-menu").fetchSemanticsNodes().isEmpty()) return
    // The scrim sits over the hamburger, so this tap lands on it.
    onNodeWithTag("hamburger-menu").performClick()
    waitUntil(5_000) {
        onAllNodesWithTag("navigation-menu").fetchSemanticsNodes().isEmpty()
    }
}

/**
 * Sign in through the menu and the real login screen, as a user would.
 * Logs a leftover session out first — earlier runs may have left one whose
 * tokens a recreate-test-users call just invalidated.
 */
fun ComposeTestRule.loginThroughTheUi(
    username: String = "test",
    password: String = "StrongTestPassword123!",
) {
    // Tests run in the app's process: kill the Credential Manager sheets
    // (saved-password offer on screen open, save-on-success) — a system
    // bottom sheet would block the driven UI outside Compose's reach.
    cz.hillview.auth.NativeAuthConfig.uiEnabled = false
    openMenu()
    if (onAllNodesWithTag("menu-logout-button").fetchSemanticsNodes().isNotEmpty()) {
        onNodeWithTag("menu-logout-button").performClick()
        waitUntil(10_000) {
            onAllNodesWithTag("navigation-menu").fetchSemanticsNodes().isEmpty()
        }
        openMenu()
        waitUntil(10_000) {
            onAllNodesWithTag("menu-login-button").fetchSemanticsNodes().isNotEmpty()
        }
    }
    onNodeWithTag("menu-login-button").performClick()
    waitUntil(10_000) {
        onAllNodesWithTag("login-username").fetchSemanticsNodes().isNotEmpty()
    }
    onNodeWithTag("login-username").performTextInput(username)
    onNodeWithTag("login-password").performTextInput(password)
    onNodeWithTag("login-submit").performClick()
    // Success pops back to Main; signed-in shows as the menu's Sign out.
    waitUntil(20_000) {
        onAllNodesWithTag("hamburger-menu").fetchSemanticsNodes().isNotEmpty()
    }
    openMenu()
    waitUntil(10_000) {
        onAllNodesWithTag("menu-logout-button").fetchSemanticsNodes().isNotEmpty()
    }
    closeMenu()
}

/**
 * The after-capture auto-upload prompt fires 800 ms behind the shutter (see
 * CaptureScreen); when a test keeps interacting after a capture it must be
 * cleared once — it is session-dismissed, so once is enough.
 */
fun ComposeTestRule.dismissAutoUploadPromptIfShown() {
    try {
        waitUntil(3_000) {
            onAllNodesWithTag("auto-upload-prompt").fetchSemanticsNodes().isNotEmpty()
        }
    } catch (_: ComposeTimeoutException) {
        return // auto-upload configured, or "never" chosen — no prompt
    }
    onNodeWithTag("dismiss-auto-upload-prompt").performClick()
    waitUntil(5_000) {
        onAllNodesWithTag("auto-upload-prompt").fetchSemanticsNodes().isEmpty()
    }
}
