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
    }

    fun inject(latitude: Double, longitude: Double) {
        locationManager.setTestProviderLocation(
            LocationManager.GPS_PROVIDER,
            Location(LocationManager.GPS_PROVIDER).apply {
                this.latitude = latitude
                this.longitude = longitude
                accuracy = 5f
                altitude = 300.0
                // Both stamps are required or the platform rejects the fix;
                // elapsedRealtimeNanos is also what hasFix freshness reads.
                time = System.currentTimeMillis()
                elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
            },
        )
    }

    fun remove() {
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

/** Home → capture, then wait out the camera cold start on the capped emulator. */
fun ComposeTestRule.openCaptureAndAwaitCamera() {
    onNodeWithTag("home-capture-button").performClick()
    waitUntil(15_000) {
        onAllNodesWithTag("capture-status").fetchSemanticsNodes().isNotEmpty()
    }
    waitUntil(45_000) {
        val status = captureStatus()
        status.isNotEmpty() && !status.contains("Starting camera")
    }
}

/** The item-13 escape hatch: no fix → capture at the map position instead. */
fun ComposeTestRule.liftGateToMapPosition() {
    waitUntil(10_000) {
        onAllNodesWithTag("capture-use-map-position").fetchSemanticsNodes().isNotEmpty()
    }
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

/**
 * Sign in through the real login screen, as a user would. Logs a leftover
 * session out first — earlier runs may have left one whose tokens a
 * recreate-test-users call just invalidated.
 */
fun ComposeTestRule.loginThroughTheUi(
    username: String = "test",
    password: String = "StrongTestPassword123!",
) {
    if (onAllNodesWithTag("home-logout-button").fetchSemanticsNodes().isNotEmpty()) {
        onNodeWithTag("home-logout-button").performClick()
        waitUntil(10_000) {
            onAllNodesWithTag("home-login-button").fetchSemanticsNodes().isNotEmpty()
        }
    }
    onNodeWithTag("home-login-button").performClick()
    waitUntil(10_000) {
        onAllNodesWithTag("login-username").fetchSemanticsNodes().isNotEmpty()
    }
    onNodeWithTag("login-username").performTextInput(username)
    onNodeWithTag("login-password").performTextInput(password)
    onNodeWithTag("login-submit").performClick()
    waitUntil(20_000) {
        onAllNodesWithTag("home-logout-button").fetchSemanticsNodes().isNotEmpty()
    }
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
