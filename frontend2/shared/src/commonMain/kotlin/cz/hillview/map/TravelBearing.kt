package cz.hillview.map

/**
 * Car mode's direction of travel, for the small arrow shown while the mount
 * offset is dragged (user, 2026-10-12: "a second small arrow would show up
 * to indicate the base direction of travel"); null where there is none.
 *
 * DERIVED — the one state's bearing with the offset taken back out — rather
 * than the engine's course read on the side, so the angle between the two
 * arrows is the offset exactly, dead-band and all.
 *
 * Only once car mode has written a heading ([TrackingPhase.Active]): before
 * that the bearing is whatever the compass last left it at, and taking an
 * offset out of it gives a direction nobody travelled.
 */
fun travelBearingFor(
    mountOffsetDrag: Boolean,
    phase: TrackingPhase,
    bearingDeg: Double,
    mountOffsetDeg: Double,
): Double? =
    if (mountOffsetDrag && phase == TrackingPhase.Active) normalizeBearing(bearingDeg - mountOffsetDeg)
    else null
