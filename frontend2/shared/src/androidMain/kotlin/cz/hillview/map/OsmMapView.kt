package cz.hillview.map

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.preference.PreferenceManager
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.tileprovider.tilesource.TileSourcePolicy
import org.osmdroid.util.GeoPoint
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import kotlin.math.cos
import kotlin.math.sin

/**
 * Turns one of our [TileProvider] entries into an osmdroid source. A template
 * source rather than XYTileSource because our palette includes URLs with a
 * query string (the TracesTrack key), which XYTileSource can't express.
 */
private class TemplateTileSource(
    private val provider: TileProvider,
) : OnlineTileSourceBase(
    provider.key,
    0,
    provider.maxNativeZoom,
    provider.tileSize,
    "",
    provider.subdomains.ifEmpty { listOf("") }.toTypedArray(),
    provider.attribution,
    TileSourcePolicy(
        2,
        TileSourcePolicy.FLAG_NO_BULK or
            TileSourcePolicy.FLAG_NO_PREVENTIVE or
            TileSourcePolicy.FLAG_USER_AGENT_MEANINGFUL,
    ),
) {
    override fun getTileURLString(pMapTileIndex: Long): String =
        provider.urlTemplate
            .replace("{s}", if (provider.subdomains.isEmpty()) "" else baseUrl)
            .replace("{z}", MapTileIndex.getZoom(pMapTileIndex).toString())
            .replace("{x}", MapTileIndex.getX(pMapTileIndex).toString())
            .replace("{y}", MapTileIndex.getY(pMapTileIndex).toString())
}

/**
 * osmdroid needs a one-time config; the user agent matters — tile servers
 * (OSM's especially) reject the library's default and hand back 403s.
 */
fun initOsmdroid(context: Context) {
    Configuration.getInstance().apply {
        load(context, PreferenceManager.getDefaultSharedPreferences(context))
        userAgentValue = context.packageName
        osmdroidBasePath = context.getExternalFilesDir(null) ?: context.filesDir
        osmdroidTileCache = osmdroidBasePath.resolve("tiles")
    }
}

fun MapView.applyProvider(provider: TileProvider) {
    setTileSource(TemplateTileSource(provider))
    // Past the provider's native depth osmdroid upscales rather than 404s,
    // matching the web app's maxZoom-above-maxNativeZoom behavior.
    maxZoomLevel = (provider.maxNativeZoom + 3).toDouble()
}

/**
 * Photo markers: a dot per photo plus a tick in the direction it was shot,
 * so coverage gaps and which way things were seen are visible at a glance.
 * Drawn as one overlay rather than N Marker objects — cheaper, and no icon
 * assets to carry.
 */
class PhotoMarkerOverlay : Overlay() {
    var markers: List<PhotoMarker> = emptyList()

    private val dotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(220, 30, 120, 255)
        style = Paint.Style.FILL
    }
    private val pendingPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(220, 255, 170, 40)
        style = Paint.Style.FILL
    }
    private val outlinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(200, 255, 255, 255)
        style = Paint.Style.STROKE
        strokeWidth = 2f
    }
    private val tickPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(200, 30, 120, 255)
        style = Paint.Style.STROKE
        strokeWidth = 3f
    }

    override fun draw(canvas: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow) return
        val projection = mapView.projection
        val point = android.graphics.Point()
        // Sizes are in dp — raw pixels vanish on a high-density screen.
        val density = mapView.context.resources.displayMetrics.density
        val dotRadius = 5f * density
        val tickLength = 18f * density
        outlinePaint.strokeWidth = 1.5f * density
        tickPaint.strokeWidth = 2f * density
        markers.forEach { marker ->
            projection.toPixels(GeoPoint(marker.latitude, marker.longitude), point)
            val x = point.x.toFloat()
            val y = point.y.toFloat()
            marker.bearingDeg?.let { bearing ->
                // Screen angles run clockwise from north, and the map itself
                // may be rotated — subtract its orientation.
                val rad = Math.toRadians(bearing - mapView.mapOrientation)
                canvas.drawLine(
                    x, y,
                    x + (sin(rad) * tickLength).toFloat(),
                    y - (cos(rad) * tickLength).toFloat(),
                    tickPaint,
                )
            }
            val paint = if (marker.uploadStatus == "completed") dotPaint else pendingPaint
            canvas.drawCircle(x, y, dotRadius, paint)
            canvas.drawCircle(x, y, dotRadius, outlinePaint)
        }
    }
}
