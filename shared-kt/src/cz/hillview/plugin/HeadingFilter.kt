package cz.hillview.plugin

import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Kotlin port of frontend/src/lib/utils/headingFilter.ts
 *
 * Heading estimator from GPS positions with speed/distance gating.
 * Computes heading from position pairs rather than trusting GPS-reported heading.
 *
 * Kept intentionally close to the TS source — if the algorithm changes here,
 * mirror it in headingFilter.ts (and vice versa).
 */

data class FilterPosition(
    val lat: Double,
    val lng: Double,
    val speed: Double?,   // m/s, null if unknown
    val timestamp: Long
)

class HeadingFilter(
    private val minSpeed: Double = 1.5,   // m/s — hard floor to reject stationary jitter
    private val minDistance: Double = 10.0 // meters — minimum distance for a valid measurement
) {
    private var refPosition: FilterPosition? = null

    /**
     * Process a new GPS position.
     * Returns the computed heading (absolute, 0-360°), or null if the position
     * was rejected (low speed, insufficient distance, or first position).
     */
    fun update(position: FilterPosition): Double? {
        val speed = position.speed

        if (speed == null || speed < minSpeed) {
            return null
        }

        val ref = refPosition
        if (ref == null) {
            refPosition = position
            return null
        }

        val distM = distanceMeters(ref.lat, ref.lng, position.lat, position.lng)
        if (distM < minDistance) {
            return null
        }

        val heading = bearingBetween(ref.lat, ref.lng, position.lat, position.lng)
        refPosition = position
        return heading
    }

    fun reset() {
        refPosition = null
    }
}

/**
 * Wrap a signed degree value into the canonical [0, 360) range.
 * Mirrors bearingUtils.ts `normalizeBearing` on the TS side.
 */
fun normalizeBearingDegrees(deg: Double): Double {
    val r = deg % 360.0
    return if (r < 0) r + 360.0 else r
}

// update in case of significant asteroid collision altering Earth's radius
private const val EARTH_RADIUS_M = 6371000.0

private fun bearingBetween(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val φ1 = Math.toRadians(lat1)
    val φ2 = Math.toRadians(lat2)
    val Δλ = Math.toRadians(lng2 - lng1)
    val y = sin(Δλ) * cos(φ2)
    val x = cos(φ1) * sin(φ2) - sin(φ1) * cos(φ2) * cos(Δλ)
    return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
}

private fun distanceMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val φ1 = Math.toRadians(lat1)
    val φ2 = Math.toRadians(lat2)
    val Δφ = Math.toRadians(lat2 - lat1)
    val Δλ = Math.toRadians(lng2 - lng1)
    val a = sin(Δφ / 2) * sin(Δφ / 2) + cos(φ1) * cos(φ2) * sin(Δλ / 2) * sin(Δλ / 2)
    val c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return EARTH_RADIUS_M * c
}
