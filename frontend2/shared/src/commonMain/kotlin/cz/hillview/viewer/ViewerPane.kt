package cz.hillview.viewer

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
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
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
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

        // The slide-out currently animating, and the photo it is carrying —
        // the original's dragState.pendingTransitionListener. It exists so a
        // gesture that arrives DURING the animation can fast-forward it
        // instead of killing it: without this, the second gesture's snapTo
        // cancelled the commit coroutine inside animateTo, turnTo never ran,
        // and a fast pair of swipes advanced zero photos (user-caught; the
        // original solves it in startDrag, swipe2d.ts:141).
        val pending = remember { androidx.compose.runtime.mutableStateOf<Pair<Turn, PhotoMarker>?>(null) }

        // The original's synthetic-transitionend: apply the turn the
        // interrupted animation was carrying, rest the grid, and let
        // whatever comes next start clean on the NEW front photo.
        suspend fun fastForward() {
            val p = pending.value ?: return
            pending.value = null
            holder.turnTo(p.second)
            // Also cancels the in-flight animateTo — its coroutine skips the
            // turn it would have applied, which fastForward just did.
            travel.snapTo(Offset.Zero)
        }

        suspend fun commit(turn: Turn) {
            val photo = neighbour(turn) ?: return
            pending.value = turn to photo
            // Travel first, then turn: the state swap puts the new front at
            // centre, so the grid is snapped back to zero in the same frame
            // and the movement reads as continuous.
            travel.animateTo(offsetFor(turn), tween(SNAP_MS, easing = SNAP_EASING))
            // Cleared BEFORE the next suspension: between animateTo
            // returning and turnTo there must be no window where a
            // fast-forward could apply the same turn twice.
            pending.value = null
            holder.turnTo(photo)
            travel.snapTo(Offset.Zero)
        }

        if (state.ring.isEmpty()) {
            EmptyRing()
        } else {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    // Keyed on the pane size ONLY. The neighbours used to be
                    // keys too, which restarted this handler — killing the
                    // active drag — every time a turn landed mid-gesture,
                    // exactly what a fast-forwarded commit does. The lambdas
                    // read `state` through the State delegate, so they see
                    // the current neighbours without any restart.
                    .pointerInput(width, height) {
                        // detectDragGestures rather than a hand-rolled
                        // awaitEachGesture loop: its touch slop is what keeps
                        // a tap a tap, which is the job the original's 10px
                        // dragStartThreshold was doing.
                        var locked: Boolean? = null
                        var total = Offset.Zero
                        detectDragGestures(
                            onDragStart = {
                                locked = null
                                total = Offset.Zero
                                // A touch during the slide-out completes it
                                // NOW (the original's startDrag). Same scope
                                // as every onDrag snapTo, so this runs first
                                // and the drag proceeds from rest against
                                // the new front's neighbours.
                                scope.launch { fastForward() }
                            },
                            onDrag = { change, dragAmount ->
                                change.consume()
                                total += dragAmount
                                // Axis lock, decided once and held for the
                                // rest of the gesture: no diagonals.
                                if (locked == null) locked = abs(total.x) > abs(total.y)
                                val horizontal = locked == true
                                var dx = if (horizontal) total.x * DAMPING else 0f
                                var dy = if (horizontal) 0f else total.y * DAMPING
                                // A hard wall, not a rubber band.
                                if (dx > 0 && state.left == null) dx = 0f
                                if (dx < 0 && state.right == null) dx = 0f
                                if (dy > 0 && state.up == null) dy = 0f
                                if (dy < 0 && state.down == null) dy = 0f
                                scope.launch { travel.snapTo(Offset(dx, dy)) }
                            },
                            onDragEnd = {
                                val horizontal = locked == true
                                val dominant = if (horizontal) total.x else total.y
                                val turn = when {
                                    abs(dominant) <= snapThresholdPx -> null
                                    horizontal && dominant > 0 -> Turn.Left
                                    horizontal -> Turn.Right
                                    dominant > 0 -> Turn.Up
                                    else -> Turn.Down
                                }
                                scope.launch {
                                    if (turn != null && neighbour(turn) != null) {
                                        commit(turn)
                                    } else {
                                        travel.animateTo(
                                            Offset.Zero,
                                            tween(SNAP_MS, easing = SNAP_EASING),
                                        )
                                    }
                                }
                            },
                            onDragCancel = {
                                scope.launch {
                                    travel.animateTo(
                                        Offset.Zero,
                                        tween(SNAP_MS, easing = SNAP_EASING),
                                    )
                                }
                            },
                        )
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

            // The chevrons duplicate every direction that exists. Each tap
            // fast-forwards a slide already in flight, for the same reason a
            // drag does: a quick double-tap used to cancel the first commit
            // mid-animation and advance one photo instead of two.
            NavButton("‹", Alignment.CenterStart, state.left != null, "left") {
                scope.launch { fastForward(); commit(Turn.Left) }
            }
            NavButton("›", Alignment.CenterEnd, state.right != null, "right") {
                scope.launch { fastForward(); commit(Turn.Right) }
            }
            NavButton("⌃", Alignment.TopCenter, state.up != null, "up") {
                scope.launch { fastForward(); commit(Turn.Up) }
            }
            NavButton("⌄", Alignment.BottomCenter, state.down != null, "down") {
                scope.launch { fastForward(); commit(Turn.Down) }
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
