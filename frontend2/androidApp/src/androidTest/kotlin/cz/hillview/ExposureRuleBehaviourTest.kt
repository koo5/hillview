package cz.hillview

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The exposure rules, at the level only a real camera can answer: that a
 * rule resolves against LIVE metering, and that turning AE off does not
 * wedge the still-capture pipeline.
 *
 * What this layer cannot show: whether a rule exposes correctly. The
 * emulated camera's scene never changes brightness and its JPEG EXIF is
 * canned — the arithmetic is PlanExposureTest's job, and the sun is the
 * field's.
 */
@RunWith(AndroidJUnit4::class)
class ExposureRuleBehaviourTest {

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
    fun aRuleResolvesAgainstLiveMeteringAndStillTakesPhotos() {
        gps.inject(50.0755, 14.4378)
        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()

        // The ⚡ control exists only where the sensor offers MANUAL_SENSOR
        // (the AVD's back camera must be `emulated`, not virtualscene).
        assumeTrue(
            "no manual sensor on this camera",
            compose.onAllNodesWithTag("shutter-speed-button")
                .fetchSemanticsNodes().isNotEmpty(),
        )

        runCatching { compose.onNodeWithTag("shutter-speed-button").performScrollTo() }
        compose.onNodeWithTag("shutter-speed-button").performClick()
        compose.onNodeWithTag("capture-exposure-mode-floor").performClick()

        // The readout appears only once the rule has a REAL reading to
        // scale from. The fabricated "plausible daylight" starting point
        // this replaced would have produced one instantly — and, in the
        // eco band that never streams a preview frame, permanently.
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("capture-exposure-plan")
                .fetchSemanticsNodes().isNotEmpty()
        }
        val readout = compose.onNodeWithTag("capture-exposure-plan")
            .fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text)
            ?.joinToString(" ") { it.text }.orEmpty()
        assertTrue("plan readout should name a gain: $readout", readout.contains("ISO"))

        // And the shutter still works with AE switched off underneath it.
        compose.onNodeWithTag("shutter-speed-button").performClick()
        compose.captureOnePhoto()
    }
}
