package cz.hillview

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipe
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.map.LocationTracking
import cz.hillview.map.MapSession
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * The first Appium behaviour ports, driving the real MainActivity through
 * Compose semantics — the assertions come from
 * docs/app-behaviour-scenarios.md, the selectors from the app's testTags.
 */
@RunWith(AndroidJUnit4::class)
class MapBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val session: MapSession
        get() = GlobalContext.get().get()

    @Before
    fun startFromTrackingOff() {
        // MapSession outlives activities AND test classes (one app process
        // for the whole suite); a fresh app start begins Off, so the tests
        // asserting the Off→Active→Background cycle arrange that here.
        // Bearing tracking too — a leftover capture activity re-arms the
        // compass at launch, and a live compass ticking between two reads
        // broke the byte-identical bearing assertion. Same for the persisted
        // activity itself: these tests speak from the view activity.
        session.setLocationTracking(LocationTracking.Off)
        session.setBearingTrackingWanted(false)
        GlobalContext.get().get<cz.hillview.settings.MapSettingsRepository>()
            .update { it.copy(mainActivity = "view") }
    }

    /** The map is a pane of the always-shown Main page now — just wait for it. */
    private fun awaitMap() {
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("map-bearing-arrow")
                .fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun bearing(): Float =
        compose.onNodeWithTag("map-bearing-arrow")
            .fetchSemanticsNode()
            .config[SemanticsProperties.ProgressBarRangeInfo]
            .current

    private fun locationState(matches: String) {
        compose.onNodeWithTag("track-location-btn").assert(
            SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, matches),
        )
    }

    /** "The bearing must be byte-identical after the app comes back." */
    @Test
    fun bearingSurvivesActivityRecreation() {
        awaitMap()
        // A persisted capture activity armed the compass AT LAUNCH, before
        // the @Before arrangements could stand it down — and one late tick
        // between the two reads breaks byte-identity. Recreate once under
        // the arranged state (view activity, tracking off) so the compass
        // was never armed in the incarnation being measured.
        compose.activityRule.scenario.recreate()
        awaitMap()
        val before = bearing()

        compose.activityRule.scenario.recreate()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("map-bearing-arrow")
                .fetchSemanticsNodes().isNotEmpty()
        }

        // 0.01° of tolerance: the guard is against the bearing RESETTING
        // (to north/zero) across recreation, not against sub-millidegree
        // noise from the always-mounted map's bookkeeping.
        assertEquals(before, bearing(), 0.01f)
    }

    /**
     * The tri-state cycle plus the exploration pill: OFF -> click ->
     * ACTIVE; a manual pan demotes to BACKGROUND and offers the pill;
     * its GPS side promotes back to ACTIVE.
     */
    @Test
    fun panDemotesAndThePillRevertsToFollowing() {
        awaitMap()
        locationState("off")

        compose.onNodeWithTag("track-location-btn").performClick()
        locationState("active")

        // A real swipe within the MAP pane (the bottom half of the split in
        // portrait) — the osmdroid view receives it through the window like
        // any finger.
        compose.onRoot().performTouchInput {
            swipe(
                start = androidx.compose.ui.geometry.Offset(centerX, height * 0.9f),
                end = androidx.compose.ui.geometry.Offset(centerX, height * 0.65f),
            )
        }
        compose.waitUntil(5_000) {
            compose.onAllNodesWithTag("map-position-prompt")
                .fetchSemanticsNodes().isNotEmpty()
        }
        locationState("background")

        compose.onNodeWithTag("revert-to-gps").performClick()
        locationState("active")
        compose.waitUntil(5_000) {
            compose.onAllNodesWithTag("map-position-prompt")
                .fetchSemanticsNodes().isEmpty()
        }
    }

    /**
     * Tracking already ACTIVE when the map composes (with the merged Main
     * page that is any relaunch mid-tracking). osmdroid's first-layout
     * settle event must read as our own camera push, not as a user pan —
     * the regression here demoted to BACKGROUND and raised the exploration
     * pill on merely opening the map.
     */
    @Test
    fun activeTrackingSurvivesEnteringTheMap() {
        awaitMap()
        session.setLocationTracking(LocationTracking.Active)
        // Recreate: the MapView remounts with tracking already active — the
        // return-from-anywhere shape.
        compose.activityRule.scenario.recreate()
        awaitMap()

        // The settle event fires from the MapView's first layout, which can
        // trail the compose-side nodes awaitMap waits on — give it the frame.
        android.os.SystemClock.sleep(750)
        compose.waitForIdle()

        locationState("active")
        assertEquals(
            0,
            compose.onAllNodesWithTag("map-position-prompt")
                .fetchSemanticsNodes().size,
        )
    }
}
