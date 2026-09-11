package cz.hillview.map

/**
 * How long the bearing arrow must be held before it will move.
 *
 * Longer than the platform's own long-press (about 400 ms is what a hand
 * reads as "held"), and comfortably longer than any brush or mis-aimed pan.
 * The point is not the duration but that there IS one: what it buys is that
 * no single touch can change where the app believes you are facing.
 */
const val ARROW_ARM_HOLD_MS = 450L

/**
 * The gate in front of manual bearing: hold the arrow, then drag it.
 *
 * A DELIBERATE divergence from the original, at the user's request
 * (2026-09-10): there, grabbing the arrow SVG sets the bearing on the spot
 * (docs/tauri-map-ui-contract.md, "Arrow grab zones"). That is one touch
 * between a measured heading and a hand-set one, on a target that was
 * invisible and straddled the green range circle, so a finger aimed at the
 * map near the arrow took the bearing with it and stood compass tracking
 * down on the way past. "Hard to pinpoint" was the report.
 *
 * The hold is also what MAKES the generous grab zone affordable. The ring is
 * a wide band across the middle of the map and it is grabbable all the way
 * round (see [bearingRingGrabbed]); that would be intolerable if landing on
 * it did something, and costs nothing when landing on it does not.
 *
 * The arming lives exactly as long as the finger — the same grammar the
 * shutter uses (hold, then choose, then release). Letting go ends manual
 * bearing mode; there is no mode to be left in by accident.
 *
 * Pure, and driven entirely by timestamps the caller supplies, so the rules
 * can be tested without a MotionEvent or a MapView.
 */
class ArrowArming(private val holdMs: Long = ARROW_ARM_HOLD_MS) {

    private var pressedAtMs: Long? = null
    private var abandonedFlag = false

    /** True once the hold has been served: drags now move the bearing. */
    var armed: Boolean = false
        private set

    /** A finger is down on the arrow, whether or not it has earned control. */
    val pressing: Boolean get() = pressedAtMs != null

    /**
     * The attempt is over but the finger has not lifted: it moved too far,
     * too early. Distinct from "no charge yet", which looks identical in
     * [progress] and means the opposite — a caller that confuses the two
     * gives up on a press that has only just begun.
     */
    val abandoned: Boolean get() = pressing && abandonedFlag

    fun press(nowMs: Long) {
        pressedAtMs = nowMs
        abandonedFlag = false
        armed = false
    }

    /**
     * Movement BEFORE the hold completes is the accident this exists to
     * catch, so it abandons the attempt rather than starting the clock
     * again — a finger sliding across the arrow must not arm at the far end
     * of its travel. After arming, movement is the whole point and is
     * ignored here.
     */
    fun moved(distancePx: Float, slopPx: Float) {
        if (armed || !pressing) return
        if (distancePx > slopPx) abandonedFlag = true
    }

    /**
     * Advance the clock. Returns true on the ONE call that arms it, so the
     * caller can fire its haptic and stand tracking down exactly once.
     */
    fun advance(nowMs: Long): Boolean {
        val at = pressedAtMs ?: return false
        if (armed || abandonedFlag) return false
        if (nowMs - at < holdMs) return false
        armed = true
        return true
    }

    /** 0 at the moment of contact, 1 when armed — what the animation draws. */
    fun progress(nowMs: Long): Float {
        val at = pressedAtMs ?: return 0f
        if (armed) return 1f
        if (abandonedFlag) return 0f
        return ((nowMs - at).toFloat() / holdMs).coerceIn(0f, 1f)
    }

    fun release() {
        pressedAtMs = null
        abandonedFlag = false
        armed = false
    }
}

/**
 * Is this touch on the bearing ring? [dx]/[dy] are the offset from the map
 * centre, [tipRadiusPx] the ring's radius, [grabPx] how far either side of
 * it still counts.
 *
 * Distance only, and deliberately so: EVERY angle grabs (user, 2026-09-10:
 * "it has to be the whole circle, i cant chase the arrow around"). It used
 * to also require being within a finger's width of the arrow line outside
 * car mode, which meant finding a moving target before a heading could be
 * set at all.
 */
fun bearingRingGrabbed(dx: Float, dy: Float, tipRadiusPx: Float, grabPx: Float): Boolean {
    if (tipRadiusPx <= 0f) return false
    val distance = kotlin.math.sqrt(dx * dx + dy * dy)
    return kotlin.math.abs(distance - tipRadiusPx) <= grabPx
}
