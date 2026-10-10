package cz.hillview.plugin

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.sqrt

/**
 * IS THE LOCAL MAGNETIC FIELD THE EARTH'S, or something nearby pretending to be?
 *
 * The compass is the only sensor that can arbitrate an azimuth, so a site where the
 * field is disturbed cannot be used to measure an azimuth fault — and the disturbance
 * does not merely offset the heading. A ferrous mass DISTORTS and TILTS the field, and
 * the fused azimuth's error then depends on how the device is HELD, because the fusion
 * resolves heading by projecting the field through the current attitude. That is the
 * exact signature a HAL azimuth fault produces, so on a disturbed site the fault and the
 * ground are indistinguishable (the Prosek Rocks lookout was rejected on this, 2026-10-10).
 *
 * Two numbers settle it, and neither needs a magnetic model:
 *
 *  - [fieldMagnitudeUt] — the field's strength. A property of the LOCATION, so it does
 *    not change as the phone turns. Prague is about 49 µT.
 *  - [fieldDipDeg] — the angle the field makes with the horizontal, from the field and
 *    GRAVITY alone. Also a property of the location, about 66° in Prague, and the more
 *    useful of the two because it is a geometric invariant: it CANNOT change when the
 *    phone is rotated, whatever the rotation. If it moves while the phone turns, either
 *    the site is disturbed or the magnetometer's own hard/soft iron is uncalibrated — and
 *    for this measurement those are the same disqualification.
 *
 * Both are computed from samples the window already carries (`accel` and `mag`), so a
 * stored sweep can be checked after the fact as well as on screen.
 */
fun fieldMagnitudeUt(mx: Float, my: Float, mz: Float): Float =
    sqrt(mx * mx + my * my + mz * mz)

/**
 * The field's dip below horizontal, degrees — positive DOWNWARD, which is the northern
 * hemisphere's sign (about +66° in Prague, +90° at the north magnetic pole, 0 at the
 * magnetic equator).
 *
 * `accel` is the accelerometer, which at rest points UP with magnitude g. The field's
 * component along up is therefore `dot(mag, up)`, and it is NEGATIVE here because the
 * field points down and north — hence the negation. Returns null when either vector is
 * too short to have a direction.
 */
fun fieldDipDeg(
    ax: Float, ay: Float, az: Float,
    mx: Float, my: Float, mz: Float,
): Float? {
    val g = sqrt(ax * ax + ay * ay + az * az)
    val b = fieldMagnitudeUt(mx, my, mz)
    if (g < 1e-3f || b < 1e-3f) return null
    // The field's share along UP, as a cosine, negated so down is positive.
    val alongUp = -((ax * mx + ay * my + az * mz) / (g * b))
    return Math.toDegrees(asin(alongUp.coerceIn(-1f, 1f)).toDouble()).toFloat()
}

/** Prague's field, for reading the two numbers above without looking anything up. */
const val FIELD_MAGNITUDE_PRAGUE_UT = 49f
const val FIELD_DIP_PRAGUE_DEG = 66f

/**
 * Is this reading consistent with the Earth's field at this latitude, within [slackUt]
 * and [slackDeg]?
 *
 * A DELIBERATELY WEAK test, and only a screening one: it catches the gross disturbance
 * that makes a site unusable, not the few degrees of heading error that would still spoil
 * a careful measurement. The decisive check is that the dip holds STILL while the phone
 * rotates, which needs a series rather than one sample — see the doc at the top. The
 * reference values are Prague's, so this is wrong elsewhere on Earth by design rather
 * than by accident; it exists to be read on a screen in one city.
 */
fun fieldLooksUndisturbed(
    magnitudeUt: Float,
    dipDeg: Float?,
    slackUt: Float = 8f,
    slackDeg: Float = 8f,
): Boolean =
    dipDeg != null &&
        abs(magnitudeUt - FIELD_MAGNITUDE_PRAGUE_UT) <= slackUt &&
        abs(dipDeg - FIELD_DIP_PRAGUE_DEG) <= slackDeg
