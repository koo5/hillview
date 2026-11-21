package cz.hillview.map

/**
 * The one boundary where pitch changes sign.
 *
 * Two conventions meet in this app and both are right in their own half:
 *
 * - **Below the one state, pitch is POSITIVE DOWN.** That is what the sensor
 *   stack measures (`asin(g_z / |g|)`, `cz.hillview.plugin.CameraPose`), what
 *   the capture stamp's `attitude.pitch_deg` carries, and what the bearings
 *   table stores beside the engine's own sensor rows.
 * - **At and above the one state, pitch is POSITIVE UP.** That is GPano's
 *   convention, which the server's `photos.pitch` has used since `f42dcceb`
 *   and which `common/capture_pose.py` derives by negating the stamp. The
 *   viewer's up/down navigation already reads server photos that way, so the
 *   state agreeing with it removes a disagreement rather than adding one.
 *
 * Everything that crosses between them goes through these two functions, so
 * that a third crossing has an obvious thing to call. There were two when this
 * was written and research found only one of them
 * (`PitchConventionTest` keeps that from happening again).
 *
 * Both are a negation. They are two names because a negation does not say
 * which way it is going, and at a call site that is the entire question.
 */

/** A sensor sample's pitch, as the one state holds it. Positive down to positive up. */
fun statePitchFromSensor(sensorDeg: Double): Double = flip(sensorDeg)

/**
 * The one state's pitch, back in the sensor's convention — for the capture
 * stamp and the bearings table, which both sit below the boundary.
 */
fun sensorPitchFromState(stateDeg: Double): Double = flip(stateDeg)

/**
 * The negation, with negative zero sent back to zero.
 *
 * `-0.0` is a real value in IEEE 754 and Kotlin prints it as "-0.0", so without
 * this a genuinely level phone reaches the bearings table, the capture stamp and
 * the exported CSV reading `-0.0` — which a person reads as a measurement leaning
 * one way and a parser may or may not. `TrackingFunnelTest` exists to say that a
 * level phone is recorded as zero rather than as absent, and it caught this.
 */
private fun flip(deg: Double): Double = if (deg == 0.0) 0.0 else -deg
