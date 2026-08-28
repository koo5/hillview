package cz.hillview.viewer

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.doubleClick
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.pinch
import androidx.compose.ui.test.swipeLeft
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.map.MapStateHolder
import cz.hillview.map.PhotoMarker
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.UploadSettingsRepository
import cz.hillview.settings.defaultUploadSettings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The inline pinch-zoom, driven by injected touches — adb cannot pinch, so
 * this is where the gesture is verified. The rules under test are the
 * original's (docs/tauri-viewer-ui-contract.md, "Pinch"): only the front
 * slot zooms, an incidental pinch snaps back, a real one stays — INLINE
 * here rather than promoted, by decision — and any turn resets it.
 */
@OptIn(ExperimentalTestApi::class)
class ViewerPaneZoomTest {

    private class FakeSettings : UploadSettingsRepository {
        private val _s = MutableStateFlow(defaultUploadSettings("https://api.test/api"))
        override val settings: StateFlow<UploadSettings> = _s
        override fun update(transform: (UploadSettings) -> UploadSettings) { _s.value = transform(_s.value) }
    }

    private class Rig {
        private fun photo(id: String, bearing: Double) = PhotoMarker(
            id = id, latitude = 50.0, longitude = 14.0, bearingDeg = bearing,
            capturedAtMs = 0L, source = "hillview",
        )

        private val keepAll = RangeCuller { photos, _, _, _, _ ->
            photos.sortedWith(compareBy({ it.bearingDeg ?: Double.MAX_VALUE }, { it.id }))
        }

        val map = MapStateHolder()
        val holder = ViewerStateHolder(
            map = map,
            standDownTracking = {},
            markers = MutableStateFlow(listOf(photo("a", 90.0), photo("b", 180.0))),
            hunterMode = MutableStateFlow(true),
            overrideFilters = MutableStateFlow(false),
            cull = keepAll,
            scope = CoroutineScope(Dispatchers.Unconfined),
            now = { 1_000L },
        )

        init {
            map.updateBearing(90.0, now = 1L)
        }
    }

    private fun androidx.compose.ui.test.ComposeUiTest.pane(rig: Rig) {
        setContent {
            ViewerPane(holder = rig.holder, settingsRepo = FakeSettings(), mapState = rig.map)
        }
    }

    private fun SemanticsNodeInteraction.zoom(): Float {
        val desc = fetchSemanticsNode().config[SemanticsProperties.StateDescription]
        return desc.removePrefix("zoom ").removeSuffix("x").toFloat()
    }

    @Test
    fun aRealPinchZoomsTheFrontAndStaysInline() = runComposeUiTest {
        pane(Rig())
        val front = onNodeWithTag("viewer-slot-front")
        assertEquals(1f, front.zoom())

        front.performTouchInput {
            // Fingers 100 px apart to 300 px apart: 3x, well past the
            // incidental threshold.
            pinch(
                center - Offset(50f, 0f), center - Offset(150f, 0f),
                center + Offset(50f, 0f), center + Offset(150f, 0f),
            )
        }
        mainClock.advanceTimeBy(500)
        val z = front.zoom()
        assertTrue(z > PINCH_PROMOTE_SCALE_FOR_TEST, "expected a real zoom, got ${z}x")
    }

    @Test
    fun anIncidentalPinchSnapsBack() = runComposeUiTest {
        pane(Rig())
        val front = onNodeWithTag("viewer-slot-front")
        front.performTouchInput {
            // 100 px to 110 px: 1.1x, under the 1.15 threshold.
            pinch(
                center - Offset(50f, 0f), center - Offset(55f, 0f),
                center + Offset(50f, 0f), center + Offset(55f, 0f),
            )
        }
        mainClock.advanceTimeBy(1_000)
        assertEquals(1f, front.zoom())
    }

    @Test
    fun aDoubleTapIsTheWayBackToOneX() = runComposeUiTest {
        pane(Rig())
        val front = onNodeWithTag("viewer-slot-front")
        front.performTouchInput {
            pinch(
                center - Offset(50f, 0f), center - Offset(150f, 0f),
                center + Offset(50f, 0f), center + Offset(150f, 0f),
            )
        }
        mainClock.advanceTimeBy(500)
        assertTrue(front.zoom() > 1f)
        front.performTouchInput { doubleClick() }
        mainClock.advanceTimeBy(1_000)
        assertEquals(1f, front.zoom())
    }

    @Test
    fun turningToANeighbourResetsTheZoom() = runComposeUiTest {
        val rig = Rig()
        pane(rig)
        val front = onNodeWithTag("viewer-slot-front")
        front.performTouchInput {
            pinch(
                center - Offset(50f, 0f), center - Offset(150f, 0f),
                center + Offset(50f, 0f), center + Offset(150f, 0f),
            )
        }
        mainClock.advanceTimeBy(500)
        assertTrue(front.zoom() > 1f)

        onNodeWithTag("viewer-nav-right").performClick()
        mainClock.advanceTimeBy(1_000)
        assertEquals("b", rig.map.bearing.value.photoUid, "the turn itself must have landed")
        assertEquals(1f, onNodeWithTag("viewer-slot-front").zoom())
    }

    /** At 1x a one-finger drag is still a swipe: the zoom must not steal it. */
    @Test
    fun atOneXASwipeStillTurns() = runComposeUiTest {
        val rig = Rig()
        pane(rig)
        onNodeWithTag("viewer-slot-front").performTouchInput { swipeLeft() }
        mainClock.advanceTimeBy(1_000)
        assertEquals("b", rig.map.bearing.value.photoUid)
    }

    private companion object {
        const val PINCH_PROMOTE_SCALE_FOR_TEST = 1.15f
    }
}
