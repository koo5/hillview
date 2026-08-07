package cz.hillview

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * The capture gating flow — camera-capture.test.ts plus the item-13
 * resolution in docs/app-behaviour-scenarios.md: the shutter requires a
 * location fix as protection for first-time users, but the requirement is
 * liftable ("I start the app when I'm somewhere underground, and I position
 * the map manually"), and lifting it is a deliberate act each visit.
 *
 * The Appium original's permission-dialog choreography is not portable:
 * GrantPermissionRule pre-grants, which is the point — this layer tests the
 * app's behaviour, not the OS dialogs.
 */
@RunWith(AndroidJUnit4::class)
class CaptureGatingBehaviourTest {

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
        // Installed before the capture screen subscribes: no fix will arrive
        // until this test says so.
        gps.install()
    }

    @After
    fun unmaskTheRealGps() {
        gps.remove()
        // Withdraw any claim this class made (claims are session-long).
        GlobalContext.get().get<cz.hillview.map.MapSession>()
            .setLocationTracking(cz.hillview.map.LocationTracking.Off)
    }

    /**
     * Phone-in-hand regression: an ACCEPTED claim (the exploration pill's
     * "Capture here") must open the gate exactly like the local lift does —
     * it used to leave the shutter shut, honoring only the lift.
     */
    @Test
    fun anAcceptedClaimOpensTheGateWithoutAFix() {
        GlobalContext.get().get<cz.hillview.map.MapSession>().claimManualPosition()
        compose.openCaptureAndAwaitCamera()

        compose.waitUntil(10_000) { compose.shutterIsEnabled() }
        // And the lift row must not double-offer while the claim stands.
        assertEquals(
            0,
            compose.onAllNodesWithTag("capture-use-map-position")
                .fetchSemanticsNodes().size,
        )
    }

    @Test
    fun gateShutsWithoutFixLiftsByHandAndOpensOnAFix() {
        compose.openCaptureAndAwaitCamera()

        // Shut: camera ready, no fix, no photo.
        val status = compose.captureStatus()
        assertTrue("expected the no-fix state, got: $status", status.contains("no GPS fix"))
        assertFalse("shutter must be gated while there is no fix", compose.shutterIsEnabled())

        // The position the lift will copy — read through the same live
        // holder the capture pane reads, before touching anything.
        val spatial = GlobalContext.get().get<cz.hillview.map.MapStateHolder>()
            .spatial.value

        // Lifted: the deliberate act opens the shutter, and the capture
        // geotags from the map position, not from any fix.
        compose.liftGateToMapPosition()
        val photo = compose.captureOnePhoto()
        assertEquals(spatial.latitude, photo.latitude, 1e-6)
        assertEquals(spatial.longitude, photo.longitude, 1e-6)

        compose.dismissAutoUploadPromptIfShown()

        // Withdrawn: requiring GPS again shuts the gate on the spot.
        runCatching { compose.onNodeWithTag("capture-manual-location").performScrollTo() }
        compose.onNodeWithTag("capture-manual-location").performClick()
        compose.waitUntil(5_000) { !compose.shutterIsEnabled() }

        // A fix opens it with no lift involved.
        gps.inject(50.0755, 14.4378)
        compose.waitUntil(15_000) {
            val s = compose.captureStatus()
            s.contains("GPS fix") && !s.contains("no GPS fix")
        }
        assertTrue("a fresh fix must open the gate", compose.shutterIsEnabled())
    }
}
