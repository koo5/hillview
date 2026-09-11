package cz.hillview.viewer

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateCentroid
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import kotlin.math.roundToInt
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
 * The original's PINCH_PROMOTE_SCALE: a pinch that ends at or below this was
 * incidental and snaps back to 1x. Above it the original PROMOTES into the
 * full zoom view; here (user-decided) the zoom simply stays inline — this
 * pane zooms, and no more. The way to the real zoom view is the ↗ link.
 */
private const val PINCH_PROMOTE_SCALE = 1.15f
private const val MAX_ZOOM = 4f

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
    settingsRepo: cz.hillview.settings.UploadSettingsRepository = org.koin.compose.koinInject(),
    mapState: cz.hillview.map.MapStateHolder = org.koin.compose.koinInject(),
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

        // The FRONT slot's inline zoom: scale about the pane's centre plus a
        // translation, both cleared by any turn. Only the front zooms — the
        // neighbours are laid out but not interactive, as in the original.
        val zoom = remember { Animatable(1f) }
        var pan by remember { mutableStateOf(Offset.Zero) }
        suspend fun resetZoom() {
            pan = Offset.Zero
            zoom.snapTo(1f)
        }

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
            resetZoom()
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
            resetZoom()
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
                Slot(
                    state.front, travel.value, Offset.Zero, width, "front",
                    zoom = zoom.value,
                    pan = pan,
                    // Pointer events reach this CHILD before the swipe
                    // handler on the parent. It consumes only while
                    // pinching or while zoomed in — so a one-finger drag at
                    // 1x falls through and swipes, a second finger landing
                    // mid-swipe cancels the swipe and zooms (the original's
                    // "pinch pre-empts"), and a one-finger drag while zoomed
                    // pans the photo instead of turning away from it.
                    gesture = Modifier
                        .pointerInput(width, height) {
                            // One loop for pinch, pan AND the double-tap
                            // that undoes them: a separate tap detector
                            // never saw a tap, because this loop had
                            // already consumed its events on the way past.
                            var lastTapAt = 0L
                            awaitEachGesture {
                                val down = awaitFirstDown(requireUnconsumed = false)
                                var pinching = false
                                var moved = false
                                var upAt = 0L
                                val slop = viewConfiguration.touchSlop
                                do {
                                    val event = awaitPointerEvent()
                                    upAt = event.changes.firstOrNull()?.uptimeMillis ?: upAt
                                    if (event.changes.count { it.pressed } >= 2) pinching = true
                                    if (!moved && event.changes.any {
                                            (it.position - down.position).getDistance() > slop
                                        }
                                    ) {
                                        moved = true
                                    }
                                    // A tap is never consumed — only a
                                    // pinch, or a drag while zoomed in.
                                    if (pinching || (zoom.value > 1f && moved)) {
                                        val s = zoom.value
                                        val s2 = (s * event.calculateZoom()).coerceIn(1f, MAX_ZOOM)
                                        // Zoom about the fingers, not the
                                        // centre: keep the image point under
                                        // the centroid where it is. With the
                                        // transform origin at the pane's
                                        // centre c and translation t, the
                                        // screen point q shows image point
                                        // c + (q - c - t) / s.
                                        val c = Offset(width / 2f, height / 2f)
                                        val q = event.calculateCentroid()
                                        var t = if (q.isSpecified) {
                                            q - c - (q - c - pan) * (s2 / s)
                                        } else {
                                            pan
                                        }
                                        t += event.calculatePan()
                                        // Nothing past the pane's edge.
                                        val maxX = (s2 - 1f) * width / 2f
                                        val maxY = (s2 - 1f) * height / 2f
                                        pan = Offset(t.x.coerceIn(-maxX, maxX), t.y.coerceIn(-maxY, maxY))
                                        scope.launch { zoom.snapTo(s2) }
                                        event.changes.forEach { it.consume() }
                                    }
                                } while (event.changes.any { it.pressed })
                                when {
                                    // Double-tap: back to 1x, the way out of
                                    // a zoom without turning away from the
                                    // photo. The interval is the platform's
                                    // own double-tap timeout.
                                    !pinching && !moved &&
                                        upAt - lastTapAt <= viewConfiguration.doubleTapTimeoutMillis -> {
                                        lastTapAt = 0L
                                        scope.launch {
                                            pan = Offset.Zero
                                            zoom.animateTo(1f, tween(SNAP_MS, easing = SNAP_EASING))
                                        }
                                    }
                                    !pinching && !moved -> lastTapAt = upAt
                                    // An incidental pinch snaps back; a real
                                    // one stays. The original's exact
                                    // threshold.
                                    zoom.value <= PINCH_PROMOTE_SCALE && zoom.value > 1f -> {
                                        scope.launch {
                                            pan = Offset.Zero
                                            zoom.animateTo(1f, tween(SNAP_MS, easing = SNAP_EASING))
                                        }
                                    }
                                }
                            }
                        },
                )
                Slot(state.left, travel.value, Offset(-width.toFloat(), 0f), width, "left")
                Slot(state.right, travel.value, Offset(width.toFloat(), 0f), width, "right")
                Slot(state.up, travel.value, Offset(0f, -height.toFloat()), width, "up")
                Slot(state.down, travel.value, Offset(0f, height.toFloat()), width, "down")
            }

            // The way out to everything this pane does not do — the zoom
            // view above all. Unobtrusive by design (user-decided): a small
            // glass chip in the corner, and only for photos that HAVE a page.
            val front = state.front
            val settings by settingsRepo.settings.collectAsState()
            val mapZoom by mapState.spatial.collectAsState()
            val webUrl = front?.let { photoWebUrl(settings.webUrl, it, mapZoom.zoom) }
            if (webUrl != null) {
                val uriHandler = LocalUriHandler.current
                Text(
                    "↗",
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(10.dp)
                        .background(Color(0x66000000), CircleShape)
                        .clickable { uriHandler.openUri(webUrl) }
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                        .testTag("viewer-open-web"),
                )
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
    zoom: Float = 1f,
    pan: Offset = Offset.Zero,
    gesture: Modifier = Modifier,
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
            .then(gesture)
            // The zoom, readable: for a screen reader, and for the UI test
            // that pinches this slot (adb cannot).
            .semantics { stateDescription = "zoom ${(zoom * 100).roundToInt() / 100f}x" }
            .testTag("viewer-slot-$tag"),
        contentAlignment = Alignment.Center,
    ) {
        if (rendition != null) {
            coil3.compose.AsyncImage(
                model = rendition.url,
                contentDescription = null,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = zoom
                        scaleY = zoom
                        translationX = pan.x
                        translationY = pan.y
                    }
                    .testTag("viewer-photo-$tag"),
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
