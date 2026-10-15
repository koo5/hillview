package cz.hillview.capture

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.v2.runComposeUiTest
import androidx.compose.ui.unit.dp
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The centre mark is CENTRED, which is the whole of its claim.
 *
 * It is the only property worth a test and the only one that can silently break: a
 * reticle two percent off centre looks perfectly convincing and makes every bearing
 * measured through it wrong by the same amount, with nothing in the photo to say so.
 * A padding added to the pane, or an alignment changed from Center while refactoring
 * the capture layout, is exactly how that happens.
 */
@OptIn(ExperimentalTestApi::class)
class ViewfinderCentreRenderTest {

    // Odd, non-square, and not divisible by the reticle's size — a mark that is centred
    // only on a tidy pane is not centred. The pane is MEASURED rather than assumed:
    // the test window clamps a pane taller than itself, and an expected centre computed
    // from the requested height then fails while the mark is perfectly placed.
    private val paneWidth = 411.dp
    private val paneHeight = 823.dp

    private fun androidx.compose.ui.test.ComposeUiTest.pane() = setContent {
        Box(Modifier.size(paneWidth, paneHeight).testTag("test-pane")) {
            ViewfinderCentre(Modifier.align(Alignment.Center))
        }
    }

    @Test
    fun theMarkSitsAtTheExactCentreOfThePane() = runComposeUiTest {
        pane()
        val pane = onNodeWithTag("test-pane").getUnclippedBoundsInRoot()
        val b = onNodeWithTag("viewfinder-centre").getUnclippedBoundsInRoot()
        assertEquals(
            (pane.left.value + pane.right.value) / 2f,
            (b.left.value + b.right.value) / 2f,
            0.5f,
        )
        assertEquals(
            (pane.top.value + pane.bottom.value) / 2f,
            (b.top.value + b.bottom.value) / 2f,
            0.5f,
        )
    }

    @Test
    fun theMarkIsDrawnAndLeavesThePointOfAimVisible() = runComposeUiTest {
        pane()
        onNodeWithTag("viewfinder-centre").assertIsDisplayed()
        val b = onNodeWithTag("viewfinder-centre").getUnclippedBoundsInRoot()
        assertEquals(VIEWFINDER_CENTRE_SIZE.value, (b.right - b.left).value, 0.5f)
        // The gap exists: a solid cross would hide the landmark being aimed at, which
        // for something on the horizon is a few pixels across.
        assertTrue(VIEWFINDER_CENTRE_GAP > 0f, "the centre must stay visible")
    }
}
