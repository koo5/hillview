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
 * Photo markers. A lone photo draws as in the Tauri app (see
 * docs/tauri-map-ui-contract.md): a cross on the GPS point, a bearing
 * circle and an arrow in the shooting direction.
 *
 * DELIBERATE DIVERGENCE: photos bunched at one viewpoint collapse into a
 * single bearing rose — one tick per photo at its own bearing, with the
 * count in the middle — instead of a pile. The Tauri app nudges every
 * marker 7px along its bearing to spread such piles, which does not scale
 * with how many share the spot and cannot separate two photos shot the same
 * way; the offset is dropped here because the rose does that job properly.
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

    /** Tapping a marker selects that photo; a rose yields its best match. */
    var onPhotoTapped: ((PhotoMarker) -> Unit)? = null

    /**
     * Where each marker ended up on screen in the last draw — the only
     * honest basis for hit testing, since a rose moves its members to the
     * group's centre and re-projecting from lat/lon would miss them.
     */
    private var lastDrawn: List<Placed> = emptyList()

    override fun onSingleTapConfirmed(event: android.view.MotionEvent?, mapView: MapView?): Boolean {
        val tap = event ?: return false
        val view = mapView ?: return false
        val handler = onPhotoTapped ?: return false
        val density = view.context.resources.displayMetrics.density
        // Generous target: the drawn glyph is ~20dp across and fingers are
        // not precise. Same spirit as the web app's 10px tap threshold.
        val radius = 24f * density

        val hit = markerAtTap(
            drawn = lastDrawn,
            tapX = tap.x,
            tapY = tap.y,
            radius = radius,
            viewBearing = viewBearing,
            x = { it.x },
            y = { it.y },
            id = { it.marker.id },
            bearing = { it.marker.bearingDeg },
        ) ?: return false

        handler(hit.marker)
        return true
    }

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
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }
    private val count = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.BLACK
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val projection = mapView.projection
        val density = mapView.context.resources.displayMetrics.density
        val point = android.graphics.Point()

        // Project once, then group anything that lands within a marker's
        // width of another. Photos from one viewpoint are the normal case,
        // so overlap is the rule rather than the exception.
        val placed = markers.map { marker ->
            projection.toPixels(GeoPoint(marker.latitude, marker.longitude), point)
            Placed(marker, point.x.toFloat(), point.y.toFloat())
        }
        val clusters = clusterByProximity(placed, 20f * density, { it.x }, { it.y })

        // Tiers, drawn back to front.
        val drawn = mutableListOf<Placed>()
        clusters.sortedBy { c ->
            when {
                c.any { it.marker.id == selectedId } -> 3
                c.any { it.marker.featured } -> 2
                c.all { it.marker.greyed } -> 0
                else -> 1
            }
        }.forEach { members ->
            val at = if (members.size == 1) {
                drawSolo(canvas, members.first(), mapView, density)
            } else {
                drawRose(canvas, members, mapView, density)
            }
            // Every member of a rose answers to the group's centre, because
            // that is the only thing on screen to aim at.
            members.forEach { drawn += Placed(it.marker, at.first, at.second) }
        }
        lastDrawn = drawn
    }

    private class Placed(val marker: PhotoMarker, val x: Float, val y: Float)

    private fun drawSolo(
        canvas: Canvas,
        placed: Placed,
        mapView: MapView,
        density: Float,
    ): Pair<Float, Float> {
        val marker = placed.marker
        val selected = marker.id == selectedId
        val bearing = marker.bearingDeg
        val rad = Math.toRadians((bearing ?: 0.0) - mapView.mapOrientation)

        // Nothing to declutter, so no offset — the arrow already says which
        // way it looks. (The Tauri app always offsets by 7px; that was a
        // stand-in for the overlap handling now done by the rose.)
        val cx = placed.x
        val cy = placed.y
        val alphaScale = if (marker.greyed) 0.45f else 1f
        val circleRadius = (if (selected) 16f else 9.6f) * density

        fill.color = circleColor(marker, alphaScale)
        canvas.drawCircle(cx, cy, circleRadius, fill)
        border.color = withAlpha(sourceColor(marker.source), alphaScale)
        border.strokeWidth = (if (selected) 3f else 1f) * density
        canvas.drawCircle(cx, cy, circleRadius, border)

        if (bearing != null) drawArrow(canvas, cx, cy, rad, density, selected, alphaScale)

        cross.strokeWidth = 1f * density
        cross.alpha = (153 * alphaScale).toInt()
        val arm = 2.5f * density
        canvas.drawLine(cx - arm, cy, cx + arm, cy, cross)
        canvas.drawLine(cx, cy - arm, cx, cy + arm, cross)
        return cx to cy
    }

    /**
     * Photos taken from (nearly) one spot become one rose: a tick per photo
     * at its own bearing, coloured by how well it agrees with the current
     * view, and the count in the middle. That answers the question the map
     * is for — "which directions from here have I already shot?" — which a
     * pile of overlapping pins cannot.
     */
    private fun drawRose(
        canvas: Canvas,
        members: List<Placed>,
        mapView: MapView,
        density: Float,
    ): Pair<Float, Float> {
        val cx = members.map { it.x }.average().toFloat()
        val cy = members.map { it.y }.average().toFloat()
        val selected = members.any { it.marker.id == selectedId }
        val featured = members.any { it.marker.featured }
        val alphaScale = if (members.all { it.marker.greyed }) 0.45f else 1f

        val outer = (if (selected) 22f else 18f) * density
        val inner = 8f * density

        // Faint disc so the rose reads as one object.
        fill.color = withAlpha(Color.WHITE, 0.75f * alphaScale)
        canvas.drawCircle(cx, cy, outer, fill)

        members.forEach { m ->
            val bearing = m.marker.bearingDeg ?: return@forEach
            val rad = Math.toRadians(bearing - mapView.mapOrientation)
            tick.color = circleColor(m.marker, alphaScale)
            tick.strokeWidth = 3.5f * density
            canvas.drawLine(
                cx + (sin(rad) * inner).toFloat(),
                cy - (cos(rad) * inner).toFloat(),
                cx + (sin(rad) * outer).toFloat(),
                cy - (cos(rad) * outer).toFloat(),
                tick,
            )
        }

        border.color = withAlpha(
            if (featured) Color.rgb(255, 215, 0) else sourceColor(members.first().marker.source),
            alphaScale,
        )
        border.strokeWidth = (if (selected) 3f else 1.5f) * density
        canvas.drawCircle(cx, cy, outer, border)

        // Count in the middle.
        fill.color = withAlpha(Color.WHITE, 0.95f * alphaScale)
        canvas.drawCircle(cx, cy, inner, fill)
        count.textSize = 11f * density
        count.alpha = (255 * alphaScale).toInt()
        val label = members.size.toString()
        canvas.drawText(
            label, cx, cy - (count.descent() + count.ascent()) / 2f, count,
        )

        cross.strokeWidth = 1f * density
        cross.alpha = (153 * alphaScale).toInt()
        val arm = 2.5f * density
        canvas.drawLine(cx - arm, cy, cx + arm, cy, cross)
        canvas.drawLine(cx, cy - arm, cx, cy + arm, cross)
        return cx to cy
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
        val a = bearingAgreementAlpha(absBearingDiff(bearing, viewBearing))
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
 * The dashed range ring. It is a **screen-constant** circle — the Tauri app
 * derives `range` from a fixed 70 CSS pixels, so the ring keeps its size
 * while zoom changes what it means on the ground. Drawn straight at that
 * pixel radius rather than round-tripping through metres, which would only
 * add projection drift.
 */
class RangeCircleOverlay : Overlay() {
    /** Screen radius in device pixels (70dp worth). */
    var radiusPx: Float = 0f
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
        if (radiusPx <= 0f) return
        val density = mapView.context.resources.displayMetrics.density
        val point = android.graphics.Point()
        mapView.projection.toPixels(c, point)

        canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), radiusPx, inner)
        // Leaflet weight/dash are CSS pixels, i.e. dp here.
        ring.strokeWidth = 8.8f * density
        ring.pathEffect = android.graphics.DashPathEffect(
            floatArrayOf(5f * density, 15f * density), 0f,
        )
        canvas.drawCircle(point.x.toFloat(), point.y.toFloat(), radiusPx, ring)
    }
}
