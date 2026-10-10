package cz.hillview.map

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.math.roundToInt
import kotlin.test.assertTrue
import org.junit.Test
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

/**
 * The cross in a photo marker marks the photo's TRUE point. The marker's
 * body is nudged 7px along the bearing to fan out piles, and the original
 * moves the cross back by the same amount (optimizedMarkers.ts:181); the
 * port drew it on the nudged centre instead, 7 dp ahead of where the photo
 * was taken (user, 2026-10-10: "are the crossess in photo markers meant to
 * signify their exact locations?").
 */
class PhotoMarkerCrossTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private val where = GeoPoint(50.08, 14.42)

    @Test
    fun theCrossSitsOnThePhotosTruePointNotTheNudgedBody() {
        initOsmdroid(context.applicationContext)
        var view: MapView? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            view = MapView(context).apply {
                measure(
                    android.view.View.MeasureSpec.makeMeasureSpec(600, android.view.View.MeasureSpec.EXACTLY),
                    android.view.View.MeasureSpec.makeMeasureSpec(600, android.view.View.MeasureSpec.EXACTLY),
                )
                layout(0, 0, 600, 600)
                controller.setZoom(17.0)
                controller.setCenter(where)
            }
        }
        val v = view!!
        val overlay = PhotoMarkerOverlay().apply {
            // Facing east, and the view facing the same way, so the body is
            // nudged 7 dp east and its fill is at full strength.
            markers = listOf(PhotoMarker(id = "p", latitude = where.latitude, longitude = where.longitude, bearingDeg = 90.0, capturedAtMs = 0L))
            viewBearing = 90.0
        }
        val bitmap = Bitmap.createBitmap(600, 600, Bitmap.Config.ARGB_8888)
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            overlay.draw(Canvas(bitmap), v, false)
        }
        val d = v.context.resources.displayMetrics.density
        val truePoint = v.projection.toPixels(where, null)
        fun px(dxDp: Float, dyDp: Float) =
            bitmap.getPixel(truePoint.x + (dxDp * d).roundToInt(), truePoint.y + (dyDp * d).roundToInt())

        // On the cross's vertical arm, 1.5 dp above the true point — inside
        // the body's fill (its centre is 7 dp east) and clear of its arrow,
        // whose back is 3.4 dp behind that centre.
        val onArm = px(0f, -1.5f)
        // The same height, 1.5 dp east: the plain fill, on neither arm.
        val plainFill = px(1.5f, -1.5f)

        assertTrue(Color.alpha(plainFill) > 0, "the probe should be inside the marker's body")
        assertTrue(
            Color.green(onArm) < Color.green(plainFill) - 80,
            "a dark cross arm should run through the true point: " +
                "on-arm ${Integer.toHexString(onArm)} vs fill ${Integer.toHexString(plainFill)}",
        )
    }
}
