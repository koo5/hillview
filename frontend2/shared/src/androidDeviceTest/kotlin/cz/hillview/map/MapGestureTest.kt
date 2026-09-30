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

    /**
     * Landing on the ring claims NOTHING, in either mode. The band is 72 dp
     * wide across the middle of the map, so a press that consumed itself
     * would cost a pan and every marker tap underneath it — which is what
     * makes a grab zone this generous affordable at all.
     */
    @Test
    fun aPressOnTheRingIsNotYetAGrab() {
        val view = mapView()
        for (hold in listOf(true, false)) {
            val overlay = BearingArrowOverlay().apply {
                tipRadiusPx = 240f
                bearingDeg = 0.0
                requireHold = hold
            }
            val down = SystemClock.uptimeMillis()
            val onTip = MotionEvent.obtain(
                down, down, MotionEvent.ACTION_DOWN,
                view.width / 2f, view.height / 2f - 240f, 0,
            )
            assertTrue(
                !overlay.onTouchEvent(onTip, view),
                "requireHold=$hold: the press must fall through to the map",
            )
        }
    }

    /**
     * With no hold to serve — the viewer, where nothing is being recorded —
     * the first MOVEMENT takes the ring and reports a bearing. That is the
     * original's behaviour, minus its tap-to-set.
     */
    @Test
    fun withoutTheHoldTheFirstMovementTurnsTheArrow() {
        val view = mapView()
        var bearings = 0
        var armed = 0
        val overlay = BearingArrowOverlay().apply {
            tipRadiusPx = 240f
            bearingDeg = 0.0
            requireHold = false
            onBearing = { bearings++ }
            onArmed = { armed++ }
        }
        val cx = view.width / 2f
        val cy = view.height / 2f
        val t = SystemClock.uptimeMillis()
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, cx, cy - 240f, 0),
            view,
        )
        // A finger sliding round the ring towards the east.
        val moved = overlay.onTouchEvent(
            MotionEvent.obtain(t, t + 16, MotionEvent.ACTION_MOVE, cx + 60f, cy - 232f, 0),
            view,
        )
        assertTrue(moved, "the drag has to be claimed, or the map pans instead")
        assertTrue(armed == 1, "manual bearing is entered exactly once, got $armed")
        assertTrue(bearings > 0, "and the bearing has to actually move")
    }

    /**
     * With the hold required — a recording activity — the same first
     * movement abandons the attempt instead of arming it, and the map keeps
     * the gesture.
     */
    @Test
    fun withTheHoldTheSameMovementIsAPanInstead() {
        val view = mapView()
        var bearings = 0
        val overlay = BearingArrowOverlay().apply {
            tipRadiusPx = 240f
            bearingDeg = 0.0
            requireHold = true
            onBearing = { bearings++ }
        }
        val cx = view.width / 2f
        val cy = view.height / 2f
        val t = SystemClock.uptimeMillis()
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, cx, cy - 240f, 0),
            view,
        )
        val moved = overlay.onTouchEvent(
            MotionEvent.obtain(t, t + 16, MotionEvent.ACTION_MOVE, cx + 60f, cy - 232f, 0),
            view,
        )
        assertTrue(!moved, "a drag that never waited belongs to the map")
        assertTrue(bearings == 0, "and must not have moved the bearing, got $bearings")
    }

    /**
     * The band is narrower where there is no hold to serve, because there it
     * is not free: a press inside it is a turn rather than a pan. 36 dp
     * either side buys nothing once landing on it costs something, so the
     * viewer uses the original's own 18.
     */
    @Test
    fun withoutTheHoldTheBandIsTheOriginalsWidth() {
        val view = mapView()
        val density = view.context.resources.displayMetrics.density
        val cx = view.width / 2f
        val cy = view.height / 2f
        // 27 dp off the ring: inside the held band, outside the viewer's.
        val offBy = 27f * density
        for (hold in listOf(true, false)) {
            val overlay = BearingArrowOverlay().apply {
                tipRadiusPx = 240f
                bearingDeg = 0.0
                requireHold = hold
            }
            val t = SystemClock.uptimeMillis()
            overlay.onTouchEvent(
                MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, cx, cy - 240f - offBy, 0),
                view,
            )
            var bearings = 0
            overlay.onBearing = { bearings++ }
            overlay.onTouchEvent(
                MotionEvent.obtain(t, t + 16, MotionEvent.ACTION_MOVE, cx + 60f, cy - 240f, 0),
                view,
            )
            // Only the no-hold case can turn on a first movement at all, so
            // this reads the near miss: it must not have taken the press.
            if (!hold) {
                assertTrue(bearings == 0, "27 dp off the ring is the map's, not the arrow's")
            }
        }
    }

    /**
     * Every angle of the ring grabs, in both modes (user, 2026-09-10: "it
     * has to be the whole circle, i cant chase the arrow around"). This used
     * to assert the opposite, back when only the arrow line was grabbable.
     */
    @Test
    fun theRingIsGrabbableAwayFromTheArrowToo() {
        val view = mapView()
        var bearings = 0
        val overlay = BearingArrowOverlay().apply {
            tipRadiusPx = 240f
            bearingDeg = 0.0 // arrow points north; the touch is due east of it
            requireHold = false
            onBearing = { bearings++ }
        }
        val cx = view.width / 2f
        val cy = view.height / 2f
        val t = SystemClock.uptimeMillis()
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t, MotionEvent.ACTION_DOWN, cx + 240f, cy, 0),
            view,
        )
        overlay.onTouchEvent(
            MotionEvent.obtain(t, t + 16, MotionEvent.ACTION_MOVE, cx + 232f, cy + 60f, 0),
            view,
        )
        assertTrue(bearings > 0, "the far side of the ring has to turn it too")
    }
}
