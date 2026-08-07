package cz.hillview.map

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
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
 * — so here the overlay claims a touch only when it lands on the grabbable
 * part, and returns false otherwise so the map gets it.
 *
 * Grab zone: the outer third of the arrow, or the whole ring in car mode,
 * where a drag reports the angle *travelled* (see the mount-offset note in
 * docs/tauri-map-ui-contract.md).
 */
class BearingArrowOverlay : Overlay() {
    var bearingDeg: Double = 141.0
    var tipRadiusPx: Float = 0f
    var fullCircleHitArea: Boolean = false

    var onDragStart: (() -> Unit)? = null
    var onBearing: ((Double) -> Unit)? = null
    var onBearingDelta: ((Double) -> Unit)? = null

    private var dragging = false
    private var previousBearing = 0.0

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
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.argb(64, 4, 5, 250)
    }
    private val centreRim = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.argb(128, 250, 0, 0)
    }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || tipRadiusPx <= 0f) return
        val density = mapView.context.resources.displayMetrics.density
        val cx = mapView.width / 2f
        val cy = mapView.height / 2f
        // The arrow points at a true-north bearing while the map itself may
        // be rotated, so draw relative to the map's orientation.
        val rad = Math.toRadians(bearingDeg - mapView.mapOrientation)
        val tipX = cx + (sin(rad) * tipRadiusPx).toFloat()
        val tipY = cy - (cos(rad) * tipRadiusPx).toFloat()

        if (fullCircleHitArea) {
            ring.strokeWidth = 4f * density
            canvas.drawCircle(cx, cy, tipRadiusPx, ring)
        }

        line.strokeWidth = 3f * density
        canvas.drawLine(cx, cy, tipX, tipY, line)

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
            fill,
        )

        canvas.drawCircle(cx, cy, 4f * density, fill)
        centreRim.strokeWidth = 1.5f * density
        canvas.drawCircle(cx, cy, 4f * density, centreRim)
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

        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val distance = hypot(e.x - cx, e.y - cy)
                val density = view.context.resources.displayMetrics.density
                val slack = 18f * density
                dragging = if (fullCircleHitArea) {
                    kotlin.math.abs(distance - tipRadiusPx) <= slack * 2
                } else {
                    distance >= tipRadiusPx * 0.6f - slack && distance <= tipRadiusPx + slack
                }
                if (!dragging) return false // let the map pan
                onDragStart?.invoke()
                previousBearing = bearingAt()
                if (!fullCircleHitArea) onBearing?.invoke(previousBearing)
                return true
            }

            MotionEvent.ACTION_MOVE -> {
                if (!dragging) return false
                val now = bearingAt()
                if (fullCircleHitArea) {
                    onBearingDelta?.invoke(angularDistance(previousBearing, now))
                    previousBearing = now
                } else {
                    onBearing?.invoke(now)
                }
                return true
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val wasDragging = dragging
                dragging = false
                return wasDragging
            }
        }
        return false
    }
}
