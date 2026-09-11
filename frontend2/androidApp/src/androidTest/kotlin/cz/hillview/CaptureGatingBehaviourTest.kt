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
import org.junit.Assume
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs
import org.koin.core.context.GlobalContext

/**
 * What a capture records for a position, and the shutter that never waits
 * for one (2026-09-09, docs/one-state.md "The position side").
 *
 * This was the capture GATING flow — camera-capture.test.ts plus the item-13
 * resolution: the shutter required a fix, liftable by hand. The gate is
 * gone: with no fix the map centre is recorded, tagged `map`, and a fix is
 * recorded as `gps` with its age; the pill's claim is the only act that
 * elects the map over a fix. The stamp table itself is pinned on the host
 * (StampPositionTest); this is the same table driven through the real
 * pane, the real pipeline and the real Room row.
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

    private val mapState: cz.hillview.map.MapStateHolder
        get() = GlobalContext.get().get()

    /**
     * Phone-in-hand regression, kept: an ACCEPTED claim (the exploration
     * pill's "Capture here") stamps the map position — it used to leave the
     * shutter shut, honouring only the pane's own lift. The shutter is live
     * regardless now; what the claim decides is the WORD and the position.
     */
    @Test
    fun anAcceptedClaimStampsTheMapPositionTaggedMap() {
        GlobalContext.get().get<cz.hillview.map.MapSession>().claimManualPosition()
        compose.openCaptureAndAwaitCamera()
        compose.waitUntil(10_000) { compose.shutterIsEnabled() }
        // The lift row is gone for good, claim or no claim.
        assertEquals(0, compose.onAllNodesWithTag("capture-use-map-position").fetchSemanticsNodes().size)

        val spatial = mapState.spatial.value
        val photo = compose.captureOnePhoto()
        compose.dismissAutoUploadPromptIfShown()
        assertEquals(spatial.latitude, photo.latitude!!, 1e-6)
        assertEquals(spatial.longitude, photo.longitude!!, 1e-6)
        assertEquals("map", photo.locationSource)
    }

    /**
     * Rows 3 and 4 of the table, no fix: a PLACED map → the map centre,
     * `map`, no button pressed; a map nobody has placed (the blank first
     * run, `SpatialState.ts` null) → no position at all, and no pretending.
     * Which row this device is on depends on its persisted map state, so
     * the test reads that and asserts the row it is actually in — both are
     * the contract, and the overlay has a note for each.
     *
     * The precondition is a fix-less SESSION, and `lastFix` is
     * process-lifetime state that any earlier class's injected fix would
     * have filled — so this says so and stands aside rather than inheriting
     * a fix and asserting the wrong row. (The host test pins every row
     * unconditionally; this is the same table through the real pane, the
     * real pipeline and the real Room row.)
     */
    @Test
    fun withNoFixTheShutterIsLiveAndThePhotoRecordsTheMapPositionOrNone() {
        Assume.assumeTrue(
            "a fix from an earlier test is in the session — these rows need none",
            mapState.lastFix.value == null,
        )
        compose.openCaptureAndAwaitCamera()
        compose.waitUntil(10_000) { compose.shutterIsEnabled() }
        assertTrue("the shutter must not wait for a fix", compose.shutterIsEnabled())
        assertEquals(0, compose.onAllNodesWithTag("capture-use-map-position").fetchSemanticsNodes().size)

        // Which row: has anyone placed the map on this device? (Every run
        // here is a fresh install — the connected-test task uninstalls the
        // app afterwards — but the map places itself on first open, so this
        // is read rather than assumed.) The overlay's note for the row is
        // NOT asserted here: the post-open hint owns the overlay for 4 s
        // after the camera comes ready, so a wait on the note races it;
        // the wording is pinned on the host instead (CameraOverlayUiTest),
        // where the hint never fires.
        val placed = mapState.spatial.value.ts != null

        val spatial = mapState.spatial.value
        val photo = compose.captureOnePhoto()
        compose.dismissAutoUploadPromptIfShown()
        if (placed) {
            assertEquals(spatial.latitude, photo.latitude!!, 1e-6)
            assertEquals(spatial.longitude, photo.longitude!!, 1e-6)
            assertEquals("map", photo.locationSource)
        } else {
            // Row 4: the one no-position case, carried as null the whole way
            // (v22) rather than as Null Island.
            assertEquals(null, photo.latitude)
            assertEquals(null, photo.longitude)
            assertEquals(null, photo.locationSource)
        }
    }

    /** Row 1: a fix, once it exists, is the position — `gps`, with an age. */
    @Test
    fun aFixIsRecordedAsGpsWhenItArrives() {
        compose.openCaptureAndAwaitCamera()
        gps.inject(50.0755, 14.4378)
        compose.waitUntil(15_000) {
            mapState.lastFix.value?.let { abs(it.latitude - 50.0755) < 1e-6 } == true
        }
        val photo = compose.captureOnePhoto()
        compose.dismissAutoUploadPromptIfShown()
        assertEquals(50.0755, photo.latitude!!, 1e-6)
        assertEquals(14.4378, photo.longitude!!, 1e-6)
        assertEquals("gps", photo.locationSource)
        assertTrue("a gps stamp carries its age", photo.locationAgeMs != null)
    }
}
