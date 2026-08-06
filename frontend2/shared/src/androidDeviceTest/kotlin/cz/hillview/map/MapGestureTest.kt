package cz.hillview.map

import android.os.SystemClock
import android.view.MotionEvent
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.math.abs
import kotlin.test.assertTrue
import org.junit.Test
import org.osmdroid.views.MapView

/**
 * The map gestures the Appium suite calls required — "pan, pinch zoom, and
 * two-finger rotate. No combination of them may wedge the map."
 *
 * These feed real MotionEvents into a real MapView rather than injecting
 * system input, so they exercise osmdroid's own detectors without needing a
 * foreground activity. That matters because the bugs being guarded here
 * were both about touches never arriving: an overlay that swallowed every
 * gesture, and a rotation nobody reported back.
 */
class MapGestureTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun mapView(): MapView {
        initOsmdroid(context.applicationContext)
        var view: MapView? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            view = MapView(context).apply {
                setMultiTouchControls(true)
                measure(
                    android.view.View.MeasureSpec.makeMeasureSpec(1080, android.view.View.MeasureSpec.EXACTLY),
                    android.view.View.MeasureSpec.makeMeasureSpec(1920, android.view.View.MeasureSpec.EXACTLY),
                )
                layout(0, 0, 1080, 1920)
            }
        }
        return view!!
    }

    /** A two-pointer event, the shape a rotate gesture is made of. */
    private fun twoFinger(
        action: Int,
        down: Long,
        first: Pair<Float, Float>,
        second: Pair<Float, Float>,
    ): MotionEvent {
        val props = arrayOf(
            MotionEvent.PointerProperties().apply { id = 0 },
            MotionEvent.PointerProperties().apply { id = 1 },
        )
        val coords = arrayOf(
            MotionEvent.PointerCoords().apply { x = first.first; y = first.second },
            MotionEvent.PointerCoords().apply { x = second.first; y = second.second },
        )
        return MotionEvent.obtain(
            down, SystemClock.uptimeMillis(), action, 2, props, coords,
            0, 0, 1f, 1f, 0, 0, 0, 0,
        )
    }

    @Test
    fun aTwoFingerTwistTurnsTheMapAndIsReported() {
        val view = mapView()
        var reported: Double? = null
        val overlay = RotationSyncOverlay(view) { reported = it }
        val down = SystemClock.uptimeMillis()

        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            view.overlays.add(overlay)
            view.dispatchTouchEvent(
                MotionEvent.obtain(down, down, MotionEvent.ACTION_DOWN, 400f, 900f, 0),
            )
            view.dispatchTouchEvent(
                twoFinger(
                    MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT),
                    down, 400f to 900f, 700f to 900f,
                ),
            )
            // Swing the second finger a quarter turn around the first.
            listOf(700f to 800f, 660f to 700f, 550f to 620f, 430f to 600f).forEach { (x, y) ->
                // osmdroid only commits the accumulated angle every 25 ms, so
                // the steps have to be spaced or the turn is swallowed.
                Thread.sleep(30)
                view.dispatchTouchEvent(
                    twoFinger(MotionEvent.ACTION_MOVE, down, 400f to 900f, x to y),
                )
            }
        }

        val turned = reported
        assertTrue(turned != null, "the rotation gesture was never reported to the store")
        assertTrue(
            abs(turned!!) > 5.0,
            "expected a visible turn from a quarter-circle twist, got $turned",
        )
        assertTrue(
            abs(view.mapOrientation.toDouble() - turned) < 1.0,
            "what was reported must be what the map actually did",
        )
    }

    @Test
    fun theBearingArrowLeavesTheMiddleOfTheMapAlone() {
        // The regression that made the map unpannable: an overlay claiming
        // touches it has no business in. A tap in the middle is nowhere near
        // the arrow's grab zone, so the overlay must decline it.
        val view = mapView()
        val overlay = BearingArrowOverlay().apply { tipRadiusPx = 240f }
        val down = SystemClock.uptimeMillis()
        val centre = MotionEvent.obtain(
            down, down, MotionEvent.ACTION_DOWN, view.width / 2f, view.height / 2f, 0,
        )

        assertTrue(
            !overlay.onTouchEvent(centre, view),
            "the arrow must not claim a touch in the middle, or the map cannot pan",
        )
    }

    @Test
    fun theBearingArrowStillClaimsItsOwnGrabZone() {
        val view = mapView()
        val overlay = BearingArrowOverlay().apply { tipRadiusPx = 240f }
        val down = SystemClock.uptimeMillis()
        // Straight up from the centre by the tip radius: on the arrow.
        val onTip = MotionEvent.obtain(
            down, down, MotionEvent.ACTION_DOWN,
            view.width / 2f, view.height / 2f - 240f, 0,
        )

        assertTrue(
            overlay.onTouchEvent(onTip, view),
            "a touch on the arrow tip has to be the arrow's, or it cannot be dragged",
        )
    }
}
