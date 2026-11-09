package cz.hillview.capture

import kotlin.math.PI
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin

/*
 * The SfM run: shots spaced by how much NEW VIEW there is, not by the clock
 * (user, 2026-11-05: "we currently support video or interval capture, but the
 * sweet spot is somewhere in the middle").
 *
 * A fixed interval is a guess at walking speed. Too long and a turning walk
 * loses the overlap a reconstruction needs — the field notes' strided walk,
 * ~14 m apart, solved to an 81 m drift where the contiguous one held at
 * 2.9 m (docs/reconstruction-field-notes.md, "Two clustering axes"). Too short
 * and standing still fills the run with copies. So the run shoots when the
 * camera has MOVED far enough or TURNED far enough since the last shot —
 * what drone mapping does by distance and photogrammetry capture apps by
 * keyframe — with a floor so a fast car cannot outrun the camera, and a
 * heartbeat so losing both signals does not stop the run.
 *
 * Everything here reads the one state (the fix's speed, the attitude) and
 * nothing here reads hardware; it is pure, and driven by times the caller
 * supplies.
 */

/**
 * How far apart an SfM run's shots are. All of it wants tuning in the field,
 * and all of it is a setting (user, 2026-11-05: "lets make it all opt-in and
 * configurable") — see MapSettings.overlapSpacing. Each trigger is OFF when
 * null.
 */
data class OverlapSpacing(
    /**
     * Ground distance between shots. The contiguous walk that solved was
     * ~1.8 m apart (a 2 s cadence at ~0.8 m/s); this is a little under it.
     */
    val metres: Double? = 1.5,
    /**
     * How far the lens may turn between shots. A phone's main camera sees
     * ~50° across in portrait, so 15° keeps ~70 % of each frame in the next —
     * a sweep on the spot stays a chain of overlapping views.
     */
    val turnDeg: Double? = 15.0,
    /** Never sooner: the fastest interval rung, and about what a phone can issue. */
    val minGapMs: Long = 200,
    /**
     * Never later: the run keeps shooting with no speed and no attitude
     * (indoors, a tunnel, a receiver that reports no speed), just sparsely.
     */
    val maxGapMs: Long? = 5_000,
)

/** Why a shot was taken — counted in the capture stats. */
enum class OverlapReason(val label: String) {
    /** The run's first shot: there is nothing yet to overlap with. */
    Start("start"),
    Moved("moved"),
    Turned("turned"),
    Heartbeat("heartbeat"),
}

/**
 * Distance travelled, from the RECEIVER's own speed rather than from the
 * positions: fused speed is Doppler-derived and steady at walking pace, while
 * position deltas at 1 Hz are mostly the fix wandering — a phone standing
 * still would walk metres a minute on its error bars alone.
 *
 * Integrated with each fix's speed held until the next one, and coasted past
 * the last fix the same way so a shot can be due between fixes; the coast is
 * capped, so a receiver that goes quiet stops adding distance.
 */
class Odometer(private val maxCoastMs: Long = 2_000) {
    private var metres = 0.0
    private var lastAtMs: Long? = null
    private var speedMps = 0.0

    /**
     * A fix arrived at [atMs] (the caller's monotonic clock). A missing speed,
     * or one no larger than its own error bar, counts as standing still: the
     * receiver has not said it is moving.
     */
    fun onFix(atMs: Long, speedMps: Float?, speedAccuracyMps: Float? = null) {
        metres = metresAt(atMs)
        lastAtMs = atMs
        val speed = speedMps?.toDouble()?.takeIf { it.isFinite() && it > 0.0 } ?: 0.0
        val noise = speedAccuracyMps?.toDouble()?.takeIf { it.isFinite() } ?: 0.0
        this.speedMps = if (speed > noise) speed else 0.0
    }

    /** Metres travelled by [nowMs]. Never decreases. */
    fun metresAt(nowMs: Long): Double {
        val at = lastAtMs ?: return metres
        val coastMs = (nowMs - at).coerceIn(0L, maxCoastMs)
        return metres + speedMps * coastMs / 1000.0
    }
}

/** Where the lens points: true heading, and tilt (positive looking down). */
data class ViewDirection(val headingDeg: Double, val pitchDeg: Double)

/** The angle between two lens directions, degrees, 0..180. Roll does not move the view. */
fun turnBetween(a: ViewDirection, b: ViewDirection): Double {
    fun unit(v: ViewDirection): Triple<Double, Double, Double> {
        val h = v.headingDeg * PI / 180
        val p = v.pitchDeg * PI / 180
        return Triple(cos(p) * sin(h), cos(p) * cos(h), -sin(p))
    }
    val (ax, ay, az) = unit(a)
    val (bx, by, bz) = unit(b)
    val dot = (ax * bx + ay * by + az * bz).coerceIn(-1.0, 1.0)
    return acos(dot) * 180 / PI
}

/**
 * Decides when the next shot is due. [shot] records each one; [due] answers,
 * for now, whether the next should go and why.
 */
class OverlapTrigger(private val spacing: OverlapSpacing = OverlapSpacing()) {
    private var shotAtMs: Long? = null
    private var shotMetres = 0.0
    private var shotView: ViewDirection? = null

    fun shot(atMs: Long, metres: Double, view: ViewDirection?) {
        shotAtMs = atMs
        shotMetres = metres
        shotView = view
    }

    /**
     * Null while the next shot is not due. A turn needs a direction at both
     * ends: with no attitude at the last shot or now, only distance and the
     * heartbeat can fire.
     */
    fun due(nowMs: Long, metres: Double, view: ViewDirection?): OverlapReason? {
        val at = shotAtMs ?: return OverlapReason.Start
        val gap = nowMs - at
        if (gap < spacing.minGapMs) return null
        val stretch = spacing.metres
        if (stretch != null && metres - shotMetres >= stretch) return OverlapReason.Moved
        val from = shotView
        val turn = spacing.turnDeg
        if (turn != null && from != null && view != null && turnBetween(from, view) >= turn) {
            return OverlapReason.Turned
        }
        val heartbeat = spacing.maxGapMs
        if (heartbeat != null && gap >= heartbeat) return OverlapReason.Heartbeat
        return null
    }
}
