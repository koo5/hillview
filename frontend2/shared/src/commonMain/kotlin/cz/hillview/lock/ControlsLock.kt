package cz.hillview.lock

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Controls locked: the app is in a pocket and every touch it receives is an
 * accident.
 *
 * The case is an interval run carried in a front pocket (user, 2026-09-11).
 * Nothing about the run needs the screen, but the run needs the ACTIVITY:
 * CameraX unbinds at `onStop`, so a sleeping screen ends the shoot. Until
 * the run can own a service lifetime of its own — a separate setting, later —
 * the screen has to stay awake, which means the screen is also touchable,
 * which is the problem this closes.
 *
 * Session-scoped, deliberately. A lock that survived a restart would greet
 * whoever relaunched the app with a locked screen and no run behind it.
 */
class ControlsLock {
    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()

    fun lock() {
        _locked.value = true
    }

    fun unlock() {
        _locked.value = false
    }
}

/**
 * What locking is allowed to do to the phone, all of it opt-in-able.
 *
 * Each of these trades something, and which trade is worth it depends on
 * hardware and habit — which is why they are settings rather than a fixed
 * policy (user: "let's have a dedicated settings screen for all this where
 * users can experiment with toggling it").
 */
data class LockOptions(
    /** Dim the backlight. The screen must stay ON; it need not be bright. */
    val dimScreen: Boolean = true,
    /** 0 = the dimmest the panel will go, 1 = untouched. */
    val brightness: Float = 0f,
    /**
     * Paint the app black while locked. Free darkness on an AMOLED, where
     * black pixels cost nothing; on an LCD the backlight is on regardless
     * and this only makes the screen harder to read on the way back in —
     * which is why it is off by default (user's distinction).
     */
    val darkTheme: Boolean = false,
    /**
     * Hide the status and navigation bars, with the system's
     * swipe-to-reveal behaviour: the first stray edge swipe then brings the
     * bars back instead of acting on them.
     */
    val hideSystemBars: Boolean = true,
    /**
     * Screen pinning (Android's lock task mode) — the ONLY thing that stops
     * home and recents, which no amount of drawing can. It is off by default
     * because it is intrusive: the system asks for confirmation, the exit is
     * a gesture the user has to know, and the device's own app-pinning
     * setting can refuse it outright.
     */
    val pinScreen: Boolean = false,
)

/**
 * How far the knob has to travel before the lock opens, as a fraction of the
 * track.
 *
 * Nearly the whole way, because the point is a gesture a pocket cannot
 * produce by accident: fabric makes short drags in arbitrary directions, not
 * one long deliberate sweep along a particular line. A slider rather than a
 * press-and-hold is the user's call, and the better one — sustained pressure
 * is exactly what a pocket DOES apply.
 */
const val UNLOCK_TRAVEL_FRACTION = 0.92f

/** Where the knob sits for a given drag, in px, never off either end. */
fun unlockKnobOffset(dragPx: Float, trackPx: Float): Float =
    dragPx.coerceIn(0f, trackPx.coerceAtLeast(0f))

/** Whether this much travel opens it. */
fun unlockReached(dragPx: Float, trackPx: Float): Boolean =
    trackPx > 0f && dragPx >= trackPx * UNLOCK_TRAVEL_FRACTION
