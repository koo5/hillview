package cz.hillview.map

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ViewConfiguration
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * The bearing arrow, drawn and handled **inside the map** rather than as a
 * Compose layer on top.
 *
 * That placement is the whole point: a full-screen Compose overlay claims
 * every touch, which silently makes the map unpannable. The original solves
 * the same problem with `pointer-events: stroke` on its SVG —
 *
 *   "Invisible ring along the range circle; pointer-events: stroke keeps the
 *    disc inside it free for map panning and marker taps"
 *
 * — so here the overlay claims a touch only once it has earned one, and
 * returns false otherwise so the map and the marker overlay get it.
 *
 * **Grab zone: the whole ring**, at the arrow's tip radius, in every mode
 * (user-asked, 2026-09-10: "it has to be the whole circle, i cant chase the
 * arrow around"). It used to be the arrow line itself outside car mode,
 * which meant finding a moving target before you could set a heading. What
 * the ring does once grabbed still differs by mode — see [mountOffsetDrag].
 *
 * Landing on the ring is not enough to move anything: the arrow has to be
 * HELD. See [ArrowArming] for why, and for what that diverges from.
 */
class BearingArrowOverlay : Overlay() {
    var bearingDeg: Double = 141.0
    var tipRadiusPx: Float = 0f

    /**
     * Car mode with GPS orientation on: a drag reports the angle TRAVELLED,
     * which becomes a mount-offset adjustment, and the arrow does not jump
     * to the finger (see the mount-offset note in
     * docs/tauri-map-ui-contract.md). Everywhere else a drag says "I am
     * facing THAT way" and the arrow goes there.
     *
     * It used to double as "the hit area is the whole ring"; the hit area is
     * the whole ring either way now, so the flag says only what it decides.
     */
    var mountOffsetDrag: Boolean = false

    /** Manual bearing has just been granted: stand the compass down, once. */
    var onArmed: (() -> Unit)? = null
    var onBearing: ((Double) -> Unit)? = null
    var onBearingDelta: ((Double) -> Unit)? = null

    private val arming = ArrowArming()
    private var downX = 0f
    private var downY = 0f

    /** Where the finger points, in true-north degrees. Kept current while a
     * finger is down so the moment of arming, which happens on a timer with
     * no MotionEvent in hand, knows where to send the arrow. */
    private var fingerBearing = 0.0
    private var armRunnable: Runnable? = null

    private val arrowBlue = Color.argb(128, 4, 5, 250)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = arrowBlue
    }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = arrowBlue
    }

    /**
     * The handle, drawn all the way round because all the way round is what
     * responds. It used to appear only in car mode, so in every other mode
     * the one control that can override the compass was invisible — the
     * other half of "hard to pinpoint" (user, 2026-09-10).
     */
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.argb(56, 4, 5, 250)
    }
    private val centreRim = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.argb(128, 250, 0, 0)
    }

    /** The hold, drawn closing on the finger; solid once it is served. */
    private val arm = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = Color.argb(220, 4, 5, 250)
    }

    /** The arrow the hold is about to produce, fading in as it charges. */
    private val ghost = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = arrowBlue
    }
    private val ghostLine = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = arrowBlue
    }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || tipRadiusPx <= 0f) return
        val density = mapView.context.resources.displayMetrics.density
        val cx = mapView.width / 2f
        val cy = mapView.height / 2f

        ring.strokeWidth = 4f * density
        canvas.drawCircle(cx, cy, tipRadiusPx, ring)

        // The arrow points at a true-north bearing while the map itself may
        // be rotated, so draw relative to the map's orientation.
        drawArrow(canvas, cx, cy, bearingDeg - mapView.mapOrientation, density, line, fill)

        canvas.drawCircle(cx, cy, 4f * density, fill)
        centreRim.strokeWidth = 1.5f * density
        canvas.drawCircle(cx, cy, 4f * density, centreRim)

        // The hold, drawn as a ring closing on the FINGER from both sides: it
        // starts as a stub under the thumb and meets itself behind the map
        // exactly when manual bearing is granted. Centred on the finger and
        // not on the arrow, because with the whole ring grabbable the finger
        // is where the answer is coming from.
        //
        // DRAWING ONLY. The moment of arming is decided by a posted callback
        // instead (see armRunnable), because arming stands compass tracking
        // down — a state write, and a state write from inside a draw pass
        // recomposes the screen that is drawing, which is the trap the
        // arrow-stamp note in MapScreen already describes.
        if (!arming.pressing) return
        val now = System.currentTimeMillis()
        val progress = arming.progress(now)
        if (progress <= 0f) return

        val fingerAngle = fingerBearing - mapView.mapOrientation

        // Where the arrow is going, shown before it goes: the press point can
        // be anywhere on the ring now, so releasing without a preview would
        // teleport the arrow to a spot the user was only resting on.
        // Not once armed: the real arrow is already there, and two arrows on
        // one heading is a smudge rather than a preview.
        if (!mountOffsetDrag && !arming.armed) {
            val alpha = (110 * progress).toInt().coerceIn(0, 255)
            ghost.alpha = alpha
            ghostLine.alpha = alpha
            drawArrow(canvas, cx, cy, fingerAngle, density, ghostLine, ghost)
        }

        arm.strokeWidth = (if (arming.armed) 5f else 3f) * density
        val sweep = 360f * progress
        canvas.drawArc(
            RectF(cx - tipRadiusPx, cy - tipRadiusPx, cx + tipRadiusPx, cy + tipRadiusPx),
            (fingerAngle - 90.0 - sweep / 2.0).toFloat(),
            sweep,
            false,
            arm,
        )
        // Keep the frames coming only while there is something to animate: an
        // armed hold is static until the finger moves.
        if (!arming.armed) mapView.postInvalidateOnAnimation()
    }

    private fun drawArrow(
        canvas: Canvas,
        cx: Float,
        cy: Float,
        angleDeg: Double,
        density: Float,
        stroke: Paint,
        solid: Paint,
    ) {
        val rad = Math.toRadians(angleDeg)
        val tipX = cx + (sin(rad) * tipRadiusPx).toFloat()
        val tipY = cy - (cos(rad) * tipRadiusPx).toFloat()
        stroke.strokeWidth = 3f * density
        canvas.drawLine(cx, cy, tipX, tipY, stroke)

        val head = 11f * density
        val backX = tipX - (sin(rad) * head).toFloat()
        val backY = tipY + (cos(rad) * head).toFloat()
        val px = cos(rad).toFloat() * head * 0.5f
        val py = sin(rad).toFloat() * head * 0.5f
        canvas.drawPath(
            Path().apply {
                moveTo(tipX, tipY)
                lineTo(backX + px, backY + py)
                lineTo(backX - px, backY - py)
                close()
            },
            solid,
        )
    }

    override fun onTouchEvent(event: MotionEvent?, mapView: MapView?): Boolean {
        val e = event ?: return false
        val view = mapView ?: return false
        val cx = view.width / 2f
        val cy = view.height / 2f

        fun bearingAt(): Double =
            normalizeBearing(
                Math.toDegrees(atan2(e.x - cx, -(e.y - cy)).toDouble()) + view.mapOrientation,
            )

        val density = view.context.resources.displayMetrics.density

        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!bearingRingGrabbed(e.x - cx, e.y - cy, tipRadiusPx, RING_GRAB_DP * density)) {
                    return false
                }
                arming.press(System.currentTimeMillis())
                downX = e.x
                downY = e.y
                fingerBearing = bearingAt()
                // A still finger sends no further events, so the moment of
                // arming has to be scheduled rather than waited for.
                cancelArmTimer(view)
                armRunnable = Runnable { arm(view) }
                    .also { view.postDelayed(it, ARROW_ARM_HOLD_MS) }
                view.postInvalidateOnAnimation()
                // NOT consumed. The ring is a wide band across the middle of
                // the map, and swallowing every touch that lands on it would
                // cost a pan and every marker tap under it. osmdroid hands
                // each overlay every event regardless of what it said last
                // time, so the hold can be timed without claiming anything —
                // and nothing IS claimed until the hold is served.
                return false
            }

            MotionEvent.ACTION_MOVE -> {
                if (!arming.pressing) return false
                if (!arming.armed) {
                    // Still earning it. The slop is the PLATFORM's, so the
                    // instant the map decides this is a pan, this decides the
                    // hold is over — one gesture cannot be both.
                    val slop = ViewConfiguration.get(view.context).scaledTouchSlop.toFloat()
                    arming.moved(hypot(e.x - downX, e.y - downY), slop)
                    if (arming.abandoned) cancelArmTimer(view)
                    fingerBearing = bearingAt()
                    view.postInvalidateOnAnimation()
                    return false
                }
                val now = bearingAt()
                if (mountOffsetDrag) {
                    onBearingDelta?.invoke(angularDistance(fingerBearing, now))
                } else {
                    onBearing?.invoke(now)
                }
                fingerBearing = now
                return true
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val wasArmed = arming.armed
                // Manual bearing lives exactly as long as the finger: there
                // is no mode left behind to be surprised by later.
                cancelArmTimer(view)
                val wasPressing = arming.pressing
                arming.release()
                if (wasPressing) view.postInvalidateOnAnimation()
                // Consumed only if it was armed — which also swallows the tap
                // the map would otherwise report, so a held ring press does
                // not select a photo marker underneath it as well.
                return wasArmed
            }
        }
        return false
    }

    private fun arm(view: MapView) {
        if (!arming.advance(System.currentTimeMillis())) return
        view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
        onArmed?.invoke()
        // The press point IS the answer in absolute mode: someone who held
        // the ring at south meant south, and making them drag a hair to
        // commit it would be a second gesture for one intention.
        if (!mountOffsetDrag) onBearing?.invoke(fingerBearing)
        view.postInvalidateOnAnimation()
    }

    private fun cancelArmTimer(view: MapView) {
        armRunnable?.let { view.removeCallbacks(it) }
        armRunnable = null
    }

    private companion object {
        /**
         * How far either side of the ring still counts as the ring, in dp.
         * Generous on purpose: it is aimed at mid-gesture, at arm's length,
         * and nothing is lost by being generous now that landing on it costs
         * nothing until the hold is served.
         */
        const val RING_GRAB_DP = 36f
    }
}
