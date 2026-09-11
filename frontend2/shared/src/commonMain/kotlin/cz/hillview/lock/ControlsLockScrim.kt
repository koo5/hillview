package cz.hillview.lock

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

/** The knob's diameter, and so the target the finger has to find. */
private val KNOB = 56.dp

/**
 * Everything the lock covers, and the one thing it does not.
 *
 * The scrim is the WHOLE window on purpose (user: "nothing else than the
 * unlock slider will be responsive"). A pocket touches everywhere, so
 * guarding one strip guards one strip; and the controls this protects are
 * scattered across both panes anyway.
 *
 * Touches are swallowed in the MAIN pointer pass, not the initial one, so
 * the slider below still gets its events first — children are dispatched
 * before their parent in that pass. Swallowing in the initial pass would
 * lock the unlock.
 */
@Composable
fun ControlsLockScrim(
    onUnlock: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BoxWithConstraints(
        modifier
            .fillMaxSize()
            // Not fully opaque: what the app is doing has to stay legible
            // through it — an interval run you cannot see is one you cannot
            // trust is still running.
            .background(Color.Black.copy(alpha = 0.55f))
            .pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        awaitPointerEvent().changes.forEach { it.consume() }
                    }
                }
            }
            .testTag("controls-lock-scrim"),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                // Well clear of every edge: the unlock drag is horizontal,
                // and a horizontal drag that STARTS at the screen edge is
                // the system's back gesture, not ours.
                .padding(horizontal = 48.dp)
                .fillMaxWidth(),
        ) {
            Text(
                "Controls locked",
                style = MaterialTheme.typography.titleMedium,
                color = Color.White,
            )
            UnlockSlider(onUnlock = onUnlock, modifier = Modifier.padding(top = 12.dp))
        }
    }
}

/**
 * Drag the knob the width of the track to unlock.
 *
 * It snaps back when released short, so a partial accident undoes itself;
 * only a sweep that lands opens the lock.
 */
@Composable
private fun UnlockSlider(
    onUnlock: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val density = LocalDensity.current
    var drag by remember { mutableStateOf(0f) }
    var trackPx by remember { mutableStateOf(0f) }
    val knobPx = with(density) { KNOB.toPx() }
    val offset by animateFloatAsState(unlockKnobOffset(drag, trackPx), label = "unlock-knob")

    BoxWithConstraints(
        modifier
            .fillMaxWidth()
            .height(KNOB)
            .background(Color.White.copy(alpha = 0.18f), RoundedCornerShape(KNOB / 2))
            .testTag("controls-unlock-slider")
            .semantics {
                stateDescription = if (trackPx > 0f) {
                    "unlock ${((drag / trackPx) * 100).roundToInt()}%"
                } else {
                    "unlock 0%"
                }
            },
        contentAlignment = Alignment.CenterStart,
    ) {
        trackPx = (with(density) { maxWidth.toPx() } - knobPx).coerceAtLeast(0f)
        Text(
            "slide to unlock",
            style = MaterialTheme.typography.labelLarge,
            color = Color.White.copy(alpha = 0.7f),
            modifier = Modifier.align(Alignment.Center),
        )
        Box(
            Modifier
                .offset { IntOffset(offset.roundToInt(), 0) }
                .size(KNOB)
                .background(Color.White.copy(alpha = 0.92f), RoundedCornerShape(KNOB / 2))
                .testTag("controls-unlock-knob")
                .pointerInput(trackPx) {
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            if (unlockReached(drag, trackPx)) onUnlock()
                            drag = 0f
                        },
                        onDragCancel = { drag = 0f },
                    ) { change, amount ->
                        change.consume()
                        drag = unlockKnobOffset(drag + amount, trackPx)
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Text("🔓", style = MaterialTheme.typography.titleMedium)
        }
    }
}
