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
import androidx.compose.ui.test.swipeUp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

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

    private fun openMap() {
        compose.onNodeWithTag("home-map-button").performClick()
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
        openMap()
        val before = bearing()

        compose.activityRule.scenario.recreate()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("map-bearing-arrow")
                .fetchSemanticsNodes().isNotEmpty()
        }

        assertEquals(before, bearing(), 0.0001f)
    }

    /**
     * The tri-state cycle plus the exploration pill: OFF -> click ->
     * ACTIVE; a manual pan demotes to BACKGROUND and offers the pill;
     * its GPS side promotes back to ACTIVE.
     */
    @Test
    fun panDemotesAndThePillRevertsToFollowing() {
        openMap()
        locationState("off")

        compose.onNodeWithTag("track-location-btn").performClick()
        locationState("active")

        // A real swipe across the map area — the osmdroid view receives it
        // through the window like any finger.
        compose.onRoot().performTouchInput { swipeUp() }
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
}
