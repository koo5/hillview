package cz.hillview.map

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.math.roundToInt
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Test
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

/**
 * The GPS accuracy disc, drawn into a bitmap off a real MapView: its edge
 * has to land where the receiver's metres land on the ground at that zoom
 * and latitude — checked against osmdroid's own metres-to-pixels, which the
 * overlay does not use, so the two cannot agree by sharing a mistake.
 */
class GpsAccuracyOverlayTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private val fix = GeoPoint(50.08, 14.42)
    private val zoom = 17.0

    private fun mapView(): MapView {
        initOsmdroid(context.applicationContext)
        var view: MapView? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            view = MapView(context).apply {
                measure(
                    android.view.View.MeasureSpec.makeMeasureSpec(1080, android.view.View.MeasureSpec.EXACTLY),
                    android.view.View.MeasureSpec.makeMeasureSpec(1920, android.view.View.MeasureSpec.EXACTLY),
                )
                layout(0, 0, 1080, 1920)
                controller.setZoom(zoom)
                controller.setCenter(fix)
            }
        }
        return view!!
    }

    /** Draws just the overlay, onto a transparent bitmap the view's size. */
    private fun render(view: MapView, overlay: GpsAccuracyOverlay): Bitmap {
        val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            overlay.draw(Canvas(bitmap), view, false)
        }
        return bitmap
    }

    private fun overlay(accuracyM: Float?) = GpsAccuracyOverlay().apply {
        position = fix
        this.accuracyM = accuracyM
        visible = true
    }

    @Test
    fun theDiscIsTheAccuracyOnTheGround() {
        val view = mapView()
        val metres = 50f
        val expected = view.projection.metersToPixels(metres, fix.latitude, zoom)
        assertTrue(expected in 40f..900f, "the zoom puts 50 m at $expected px — pick one that fits the view")
        val bitmap = render(view, overlay(metres))
        val centre = view.projection.toPixels(fix, null)
        val margin = 4 * view.context.resources.displayMetrics.density

        // East and north: the same radius both ways, inside tinted, outside clear.
        for ((dx, dy) in listOf(1 to 0, 0 to -1)) {
            val inside = Color.alpha(
                bitmap.getPixel(
                    centre.x + (dx * (expected - margin)).roundToInt(),
                    centre.y + (dy * (expected - margin)).roundToInt(),
                ),
            )
            val outside = Color.alpha(
                bitmap.getPixel(
                    centre.x + (dx * (expected + margin)).roundToInt(),
                    centre.y + (dy * (expected + margin)).roundToInt(),
                ),
            )
            assertTrue(inside in 0x30..0x50, "($dx,$dy) just inside the edge should be the fill, alpha $inside")
            assertEquals(0, outside, "($dx,$dy) just outside the edge should be untouched")
        }
        assertTrue(
            Color.alpha(bitmap.getPixel(centre.x, centre.y)) in 0x30..0x50,
            "the fix itself sits in the fill",
        )
    }

    @Test
    fun noAccuracyDrawsNothing() {
        val view = mapView()
        for (accuracy in listOf(null, 0f, Float.NaN)) {
            val bitmap = render(view, overlay(accuracy))
            val centre = view.projection.toPixels(fix, null)
            assertEquals(0, Color.alpha(bitmap.getPixel(centre.x, centre.y)), "accuracy $accuracy")
        }
    }

    @Test
    fun trackingOffDrawsNothing() {
        val view = mapView()
        val bitmap = render(view, overlay(50f).apply { visible = false })
        val centre = view.projection.toPixels(fix, null)
        assertEquals(0, Color.alpha(bitmap.getPixel(centre.x, centre.y)))
    }
}
