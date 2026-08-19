package cz.hillview.viewer

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.AnimationVector2D
import androidx.compose.animation.core.VectorConverter
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import cz.hillview.map.PhotoMarker
import cz.hillview.map.pickRendition
import kotlinx.coroutines.launch
import kotlin.math.abs

/** Which way a swipe went, in photo terms rather than finger terms. */
private enum class Turn { Left, Right, Up, Down }

// From docs/tauri-viewer-ui-contract.md — the Svelte swipe2d's constants.
private val DRAG_START_THRESHOLD = 10.dp
private val SNAP_THRESHOLD = 50.dp
private const val DAMPING = 1.0f
private const val SNAP_MS = 300
private val SNAP_EASING = CubicBezierEasing(0.2f, 0.8f, 0.2f, 1f)

/**
 * The viewer pane: the photo you are facing, with the four you can turn to
 * one swipe away. See docs/tauri-viewer-ui-contract.md — this is its layout
 * and gestures; the rules behind it are ViewerRules/ViewerState.
 *
 * Not a gallery, despite the original's component name. Turning to a
 * neighbour is a BEARING WRITE, so the map turns with you.
 */
@Composable
fun ViewerPane(
    modifier: Modifier = Modifier,
    holder: ViewerStateHolder = org.koin.compose.koinInject(),
) {
    val state by holder.state.collectAsStateWithLifecycle()

    BoxWithConstraints(
        modifier = modifier.fillMaxSize().testTag("viewer-pane"),
    ) {
        val width = constraints.maxWidth
        val height = constraints.maxHeight
        val scope = rememberCoroutineScope()
        // The grid's travel. Zero means the front slot fills the pane; the
        // neighbours sit exactly one pane-width or -height away, as in the
        // original's 300%-wide grid offset by -100%.
        val travel = remember { Animatable(Offset.Zero, Offset.VectorConverter) }

        val density = androidx.compose.ui.platform.LocalDensity.current
        val startThresholdPx = with(density) { DRAG_START_THRESHOLD.toPx() }
        val snapThresholdPx = with(density) { SNAP_THRESHOLD.toPx() }

        // A turn moves the grid the other way: the photo on the right arrives
        // by the grid sliding left.
        fun offsetFor(turn: Turn) = when (turn) {
            Turn.Left -> Offset(width.toFloat(), 0f)
            Turn.Right -> Offset(-width.toFloat(), 0f)
            Turn.Up -> Offset(0f, height.toFloat())
            Turn.Down -> Offset(0f, -height.toFloat())
        }

        fun neighbour(turn: Turn): PhotoMarker? = when (turn) {
            Turn.Left -> state.left
            Turn.Right -> state.right
            Turn.Up -> state.up
            Turn.Down -> state.down
        }

        suspend fun commit(turn: Turn) {
            val photo = neighbour(turn) ?: return
            // Travel first, then turn: the state swap puts the new front at
            // centre, so the grid is snapped back to zero in the same frame
            // and the movement reads as continuous.
            travel.animateTo(offsetFor(turn), tween(SNAP_MS, easing = SNAP_EASING))
            holder.turnTo(photo)
            travel.snapTo(Offset.Zero)
        }

        if (state.ring.isEmpty()) {
            EmptyRing()
        } else {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .pointerInput(state.left, state.right, state.up, state.down, width, height) {
                        awaitEachGesture {
                            awaitFirstDown(requireUnconsumed = false)
                            var locked: Boolean? = null // true = horizontal
                            var total = Offset.Zero
                            var moved = false

                            while (true) {
                                val event = awaitPointerEvent()
                                val change: PointerInputChange =
                                    event.changes.firstOrNull() ?: break
                                if (!change.pressed) break

                                total += change.positionChange()
                                if (!moved && total.getDistance() >= startThresholdPx) {
                                    moved = true
                                    // Axis lock, decided once and held: no
                                    // diagonals, no changing your mind.
                                    locked = abs(total.x) > abs(total.y)
                                }
                                if (moved) {
                                    val horizontal = locked == true
                                    var dx = if (horizontal) total.x * DAMPING else 0f
                                    var dy = if (horizontal) 0f else total.y * DAMPING
                                    // A hard wall, not a rubber band: dragging
                                    // toward a direction with no photo does
                                    // not move at all.
                                    if (dx > 0 && state.left == null) dx = 0f
                                    if (dx < 0 && state.right == null) dx = 0f
                                    if (dy > 0 && state.up == null) dy = 0f
                                    if (dy < 0 && state.down == null) dy = 0f
                                    change.consume()
                                    scope.launch { travel.snapTo(Offset(dx, dy)) }
                                }
                            }

                            scope.launch {
                                val horizontal = locked == true
                                val dominant = if (horizontal) total.x else total.y
                                val turn = when {
                                    !moved || abs(dominant) <= snapThresholdPx -> null
                                    horizontal && dominant > 0 -> Turn.Left
                                    horizontal -> Turn.Right
                                    dominant > 0 -> Turn.Up
                                    else -> Turn.Down
                                }
                                if (turn != null && neighbour(turn) != null) {
                                    commit(turn)
                                } else {
                                    travel.animateTo(
                                        Offset.Zero,
                                        tween(SNAP_MS, easing = SNAP_EASING),
                                    )
                                }
                            }
                        }
                    },
            ) {
                // Every slot is PANE-SIZED, including the neighbours: the
                // swipe reveals an image already loaded at display size,
                // which is what the original's 300% grid buys.
                Slot(state.front, travel.value, Offset.Zero, width, "front")
                Slot(state.left, travel.value, Offset(-width.toFloat(), 0f), width, "left")
                Slot(state.right, travel.value, Offset(width.toFloat(), 0f), width, "right")
                Slot(state.up, travel.value, Offset(0f, -height.toFloat()), width, "up")
                Slot(state.down, travel.value, Offset(0f, height.toFloat()), width, "down")
            }

            // The chevrons duplicate every direction that exists.
            NavButton("‹", Alignment.CenterStart, state.left != null, "left") {
                scope.launch { commit(Turn.Left) }
            }
            NavButton("›", Alignment.CenterEnd, state.right != null, "right") {
                scope.launch { commit(Turn.Right) }
            }
            NavButton("⌃", Alignment.TopCenter, state.up != null, "up") {
                scope.launch { commit(Turn.Up) }
            }
            NavButton("⌄", Alignment.BottomCenter, state.down != null, "down") {
                scope.launch { commit(Turn.Down) }
            }
        }
    }
}

@Composable
private fun Slot(
    photo: PhotoMarker?,
    travel: Offset,
    home: Offset,
    containerWidthPx: Int,
    tag: String,
) {
    if (photo == null) return
    val rendition = remember(photo, containerWidthPx) { photo.pickRendition(containerWidthPx) }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .offset {
                IntOffset(
                    (home.x + travel.x).toInt(),
                    (home.y + travel.y).toInt(),
                )
            }
            .testTag("viewer-slot-$tag"),
        contentAlignment = Alignment.Center,
    ) {
        if (rendition != null) {
            coil3.compose.AsyncImage(
                model = rendition.url,
                contentDescription = null,
                modifier = Modifier.fillMaxSize().testTag("viewer-photo-$tag"),
                contentScale = androidx.compose.ui.layout.ContentScale.Fit,
            )
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.BoxScope.NavButton(
    glyph: String,
    alignment: Alignment,
    enabled: Boolean,
    tag: String,
    onClick: () -> Unit,
) {
    if (!enabled) return
    TextButton(
        onClick = onClick,
        modifier = Modifier.align(alignment).padding(4.dp).testTag("viewer-nav-$tag"),
    ) {
        Text(glyph, style = MaterialTheme.typography.headlineMedium)
    }
}

@Composable
private fun EmptyRing() {
    Column(
        modifier = Modifier.fillMaxSize().testTag("viewer-empty"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "No photos within the range circle",
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            "Try zooming out or panning the map",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
