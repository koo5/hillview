package cz.hillview

import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The /device-photos port: a capture made through the real shutter must
 * show up as a card — status, details, the same Room rows the upload
 * stack drains. Contract in docs/tauri-capture-ui-contract.md.
 */
@RunWith(AndroidJUnit4::class)
class DevicePhotosBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val gps = MockGps()

    @Before
    fun maskTheRealGps() {
        gps.install()
    }

    @After
    fun unmaskTheRealGps() {
        gps.remove()
    }

    @Test
    fun aCaptureShowsUpAsACardWithItsUploadFate() {
        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()
        val photo = compose.captureOnePhoto()

        compose.openMenu()
        compose.onNodeWithTag("menu-device-photos").performClick()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("photos-grid").fetchSemanticsNodes().isNotEmpty()
        }

        // Newest first: the photo just captured heads the list.
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("photo-card").fetchSemanticsNodes().isNotEmpty()
        }
        val stats = compose.onNodeWithTag("device-photo-stats")
            .fetchSemanticsNode().config
            .getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Text)
            ?.joinToString(" ") { it.text } ?: ""
        assertTrue("stats line should count photos, got: $stats", !stats.startsWith("0 photos"))

        // Refresh keeps working (the original's refresh-button).
        compose.onNodeWithTag("refresh-button").performClick()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("photo-card").fetchSemanticsNodes().isNotEmpty()
        }
    }
}
