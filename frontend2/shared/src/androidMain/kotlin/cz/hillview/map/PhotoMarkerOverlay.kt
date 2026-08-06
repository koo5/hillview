package cz.hillview.map

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.cos
import kotlin.math.sin

/**
 * Photo markers, matching the Tauri app's DivIcon (see
 * docs/tauri-map-ui-contract.md):
 *
 *  - a small cross exactly on the GPS point,
 *  - a bearing circle pushed 7 dp forward along the photo's bearing,
 *  - an arrow in that direction.
 *
 * The circle's fill is how closely the photo's bearing agrees with the
 * current view bearing (opaque green when aligned, fading as it diverges);
 * its border is the source colour; featured photos are gold and never
 * recoloured. Greyed photos are drawn washed out. Draw order stands in for
 * the z-index tiers: filtered < regular < featured < selected.
 */
class PhotoMarkerOverlay : Overlay() {
    var markers: List<PhotoMarker> = emptyList()
    var viewBearing: Double = 0.0
    var selectedId: String? = null

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val cross = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.argb(153, 0, 0, 0)
    }
    private val arrowFill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.WHITE
    }
    private val arrowStroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val projection = mapView.projection
        val density = mapView.context.resources.displayMetrics.density
        val point = android.graphics.Point()

        // Tiers, drawn back to front.
        val ordered = markers.sortedBy {
            when {
                it.id == selectedId -> 3
                it.featured -> 2
                it.greyed -> 0
                else -> 1
            }
        }

        ordered.forEach { marker ->
            projection.toPixels(GeoPoint(marker.latitude, marker.longitude), point)
            val gx = point.x.toFloat()
            val gy = point.y.toFloat()
            val selected = marker.id == selectedId
            val bearing = marker.bearingDeg
            // Screen angle: the map may be rotated under us.
            val rad = Math.toRadians((bearing ?: 0.0) - mapView.mapOrientation)

            // The circle+arrow sit 7dp ahead of the photo's position; the
            // cross stays on it.
            val offset = if (bearing == null) 0f else 7f * density
            val cx = gx + (sin(rad) * offset).toFloat()
            val cy = gy - (cos(rad) * offset).toFloat()

            val alphaScale = if (marker.greyed) 0.45f else 1f
            val circleRadius = (if (selected) 16f else 9.6f) * density

            fill.color = circleColor(marker, alphaScale)
            canvas.drawCircle(cx, cy, circleRadius, fill)

            border.color = withAlpha(sourceColor(marker.source), alphaScale)
            border.strokeWidth = (if (selected) 3f else 1f) * density
            canvas.drawCircle(cx, cy, circleRadius, border)

            if (bearing != null) {
                drawArrow(canvas, cx, cy, rad, density, selected, alphaScale)
            }

            // Cross on the true position (5dp, 1dp bars).
            cross.strokeWidth = 1f * density
            cross.alpha = (153 * alphaScale).toInt()
            val arm = 2.5f * density
            canvas.drawLine(gx - arm, gy, gx + arm, gy, cross)
            canvas.drawLine(gx, gy - arm, gx, gy + arm, cross)
        }
    }

    private fun drawArrow(
        canvas: Canvas,
        cx: Float,
        cy: Float,
        rad: Double,
        density: Float,
        selected: Boolean,
        alphaScale: Float,
    ) {
        val scale = (if (selected) 1.2f else 1f) * density
        val tipR = 11.2f * scale
        val baseR = 5.6f * scale
        val tip = floatArrayOf(
            cx + (sin(rad) * tipR).toFloat(),
            cy - (cos(rad) * tipR).toFloat(),
        )
        val backX = cx - (sin(rad) * baseR * 0.6f).toFloat()
        val backY = cy + (cos(rad) * baseR * 0.6f).toFloat()
        val px = cos(rad).toFloat() * baseR * 0.6f
        val py = sin(rad).toFloat() * baseR * 0.6f
        val path = Path().apply {
            moveTo(tip[0], tip[1])
            lineTo(backX + px, backY + py)
            lineTo(backX - px, backY - py)
            close()
        }
        arrowFill.alpha = (179 * alphaScale).toInt()
        canvas.drawPath(path, arrowFill)
        arrowStroke.color = Color.BLACK
        arrowStroke.alpha = (179 * alphaScale).toInt()
        arrowStroke.strokeWidth = 1.2f * density
        canvas.drawPath(path, arrowStroke)
    }

    /**
     * `hsla(120,100%,70%, 1/step)` with `step = round(diff / 28.57)` — the
     * original's bearing-agreement ramp. Featured photos stay gold.
     */
    private fun circleColor(marker: PhotoMarker, alphaScale: Float): Int {
        if (marker.featured) return withAlpha(Color.rgb(255, 215, 0), alphaScale * 0.8f)
        val bearing = marker.bearingDeg
            ?: return withAlpha(Color.rgb(158, 158, 158), alphaScale * 0.8f)
        val step = Math.round(absBearingDiff(bearing, viewBearing) / (200.0 / 7.0)).toInt()
        val a = if (step > 0) 1f / step else 1f
        // hsl(120,100%,70%) = #66FF66
        return withAlpha(Color.rgb(102, 255, 102), a * 0.8f * alphaScale)
    }

    private fun sourceColor(source: String?): Int = when (source) {
        "mapillary" -> Color.rgb(136, 136, 136)
        "panoramax" -> Color.rgb(51, 170, 136)
        "device" -> Color.rgb(74, 226, 77)
        "hillview" -> Color.BLACK
        else -> Color.rgb(102, 102, 102)
    }

    private fun withAlpha(color: Int, alpha: Float): Int =
        Color.argb(
            (255 * alpha.coerceIn(0f, 1f)).toInt(),
            Color.red(color),
            Color.green(color),
            Color.blue(color),
        )
}

/**
 * The dashed range ring: everything inside it is "in range" for navigation
 * and greying, and its edge is where the bearing arrow points.
 */
class RangeCircleOverlay : Overlay() {
    /** Metres; the caller keeps this equal to 70 screen pixels. */
    var radiusMeters: Double = 1000.0
    var centre: GeoPoint? = null
    var visible: Boolean = true

    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = Color.rgb(0x4A, 0xE0, 0x92)
    }
    private val inner = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.argb(51, 255, 255, 255)
    }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || !visible) return
        val c = centre ?: return
        val density = mapView.context.resources.displayMetrics.density
        val point = android.graphics.Point()
        mapView.projection.toPixels(c, point)
        // Metres → pixels through the projection's own scale.
        val edge = c.destinationPoint(radiusMeters, 90.0)
        val edgePoint = android.graphics.Point()
        mapView.projection.toPixels(edge, edgePoint)
        val radiusPx = kotlin.math.hypot(
            (edgePoint.x - point.x).toDouble(),
            (edgePoint.y - point.y).toDouble(),
        ).toFloat()
        if (radiusPx <= 0f) return

        canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), radiusPx, inner)
        ring.strokeWidth = 8.8f * density / 2.75f
        ring.pathEffect = android.graphics.DashPathEffect(
            floatArrayOf(5f * density, 15f * density), 0f,
        )
        canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), radiusPx, ring)
    }
}
