package cz.hillview.map

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.os.SystemClock
import android.view.MotionEvent
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Test
import org.osmdroid.views.MapView

/**
 * Car mode's direction of travel, drawn as a second, smaller arrow while the
 * ring is held for a mount-offset drag (user, 2026-10-12: "a second small
 * arrow would show up to indicate the base direction of travel").
 *
 * Rendered into a bitmap off a real MapView, with real touches. The blue
 * arrow points north and the travel east, so a pixel due east of the centre
 * belongs to the travel arrow and to nothing else.
 */
class TravelArrowTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val ring = 240f

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
            }
        }
        return view!!
    }

    private fun overlay(offsetDrag: Boolean, hold: Boolean, travel: Double? = 90.0) =
        BearingArrowOverlay().apply {
            ringRadiusPx = ring
            bearingDeg = 0.0
            mountOffsetDrag = offsetDrag
            requireHold = hold
            travelBearingDeg = travel
        }

    /** Just the overlay, onto a transparent bitmap the view's size. */
    private fun render(view: MapView, overlay: BearingArrowOverlay): Bitmap {
        val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            overlay.draw(Canvas(bitmap), view, false)
        }
        return bitmap
    }

    /** Halfway along the travel arrow's shaft, due east of the centre. */
    private fun travelShaft(view: MapView, bitmap: Bitmap): Int =
        bitmap.getPixel((view.width / 2f + ring * 0.3f).toInt(), view.height / 2)

    private fun press(view: MapView, overlay: BearingArrowOverlay, t: Long) {
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, view.width / 2f, view.height / 2f - ring, 0),
            view,
        )
    }

    private fun drag(view: MapView, overlay: BearingArrowOverlay, t: Long) {
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t + 16, MotionEvent.ACTION_MOVE, view.width / 2f + 60f, view.height / 2f - 232f, 0),
            view,
        )
    }

    private fun lift(view: MapView, overlay: BearingArrowOverlay, t: Long) {
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t + 32, MotionEvent.ACTION_UP, view.width / 2f + 60f, view.height / 2f - 232f, 0),
            view,
        )
    }

    @Test
    fun theOffsetDragShowsTheDirectionOfTravelAndLettingGoHidesIt() {
        val view = mapView()
        val overlay = overlay(offsetDrag = true, hold = false)
        assertEquals(0, Color.alpha(travelShaft(view, render(view, overlay))), "nothing before the ring is touched")

        val t = SystemClock.uptimeMillis()
        press(view, overlay, t)
        drag(view, overlay, t)
        val shaft = travelShaft(view, render(view, overlay))
        assertTrue(Color.alpha(shaft) > 120, "the travel arrow shows while dragging, alpha ${Color.alpha(shaft)}")
        assertTrue(
            Color.blue(shaft) < 100,
            "and it is not the blue of the heading: ${Integer.toHexString(shaft)}",
        )

        lift(view, overlay, t)
        assertEquals(0, Color.alpha(travelShaft(view, render(view, overlay))), "gone once the finger lifts")
    }

    @Test
    fun withNoHoldATouchThatHasNotMovedShowsNothing() {
        // In the viewer a press on the ring may still be a tap on a marker
        // under it; the drag begins with the first movement, and so does this.
        val view = mapView()
        val overlay = overlay(offsetDrag = true, hold = false)
        press(view, overlay, SystemClock.uptimeMillis())
        assertEquals(0, Color.alpha(travelShaft(view, render(view, overlay))))
    }

    @Test
    fun withTheHoldItComesInAsTheHoldCharges() {
        val view = mapView()
        val overlay = overlay(offsetDrag = true, hold = true)
        press(view, overlay, SystemClock.uptimeMillis())
        val early = Color.alpha(travelShaft(view, render(view, overlay)))
        Thread.sleep(ARROW_ARM_HOLD_MS + 50)
        val served = Color.alpha(travelShaft(view, render(view, overlay)))
        assertTrue(early < 80, "barely there as the hold begins, alpha $early")
        assertTrue(served > 120, "fully there once it is served, alpha $served")
    }

    @Test
    fun onlyAMountOffsetDragWithACourseShowsIt() {
        val view = mapView()
        for ((offsetDrag, travel) in listOf(false to 90.0, true to null)) {
            val overlay = overlay(offsetDrag = offsetDrag, hold = false, travel = travel)
            val t = SystemClock.uptimeMillis()
            press(view, overlay, t)
            drag(view, overlay, t)
            assertEquals(
                0,
                Color.alpha(travelShaft(view, render(view, overlay))),
                "offsetDrag=$offsetDrag travel=$travel",
            )
        }
    }
}
