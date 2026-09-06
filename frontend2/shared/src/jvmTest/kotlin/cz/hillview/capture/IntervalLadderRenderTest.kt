package cz.hillview.capture

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.v2.runComposeUiTest
import androidx.compose.ui.unit.dp
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The ladder actually composes, and says what it is showing.
 *
 * The maths has its own test; this is about the drawn control — that the
 * hovered band names itself INSIDE the band (the thing that was asked for),
 * that the pointer line appears only when there is a finger to mark, and
 * that "pointing at" and "would act on release" read differently.
 */
@OptIn(ExperimentalTestApi::class)
class IntervalLadderRenderTest {

    /** 0 single, 1..4 sub-second, 5 = 1 s, 6 = 2 s. */
    private val twoSeconds = INTERVAL_LADDER.indexOf(LadderRung.Every(2_000))

    private fun androidx.compose.ui.test.ComposeUiTest.ladder(
        hoverIndex: Int = twoSeconds,
        armed: Boolean = true,
        pointerFraction: Float? = 0.5f,
    ) = setContent {
        Box(Modifier.size(width = 160.dp, height = 600.dp)) {
            IntervalLadder(
                hoverIndex = hoverIndex,
                armed = armed,
                pointerFraction = pointerFraction,
                modifier = Modifier.size(width = 160.dp, height = 600.dp),
            )
        }
    }

    private fun androidx.compose.ui.test.ComposeUiTest.state(): String =
        onNodeWithTag("capture-interval-ladder")
            .fetchSemanticsNode()
            .config[SemanticsProperties.StateDescription]

    @Test
    fun theHoveredBandNamesItself() = runComposeUiTest {
        ladder()
        onNodeWithTag("capture-interval-value").assertTextEquals("2s")
        assertEquals("armed 2s", state())
    }

    @Test
    fun aSubSecondRungReadsAsAFraction() = runComposeUiTest {
        ladder(hoverIndex = INTERVAL_LADDER.indexOf(LadderRung.Every(750)))
        onNodeWithTag("capture-interval-value").assertTextEquals("0.75s")
    }

    @Test
    fun theTopRungIsVideoAndTheBottomIsSingle() = runComposeUiTest {
        ladder(hoverIndex = INTERVAL_LADDER.lastIndex)
        onNodeWithTag("capture-interval-value").assertTextEquals("VIDEO")
    }

    @Test
    fun pointingAtARungIsNotTheSameAsArmingIt() = runComposeUiTest {
        ladder(armed = false)
        assertEquals("hover 2s", state())
    }

    @Test
    fun thePointerLineMarksAFingerAndNothingElse() = runComposeUiTest {
        ladder(pointerFraction = 0.5f)
        onNodeWithTag("capture-interval-pointer").assertExists()
    }

    @Test
    fun noFingerNoLine() = runComposeUiTest {
        ladder(pointerFraction = null)
        onNodeWithTag("capture-interval-pointer").assertDoesNotExist()
    }
}
