package cz.hillview.map

/*
 * Where each part of the one circle on the map sits, measured from the range
 * THRESHOLD: the radius at which a photo stops being in range.
 *
 * The user's rule (2026-10-10): "the circle should give users the exact
 * threshold of the range. and the bearing arrow should end right inside it".
 * So the circle IS the threshold — one thin solid line — and nothing else
 * drawn crosses it: the arrow stays wholly inside, the bearing hold wholly
 * outside.
 *
 * There used to be a dashed band as well, Leaflet's `weight 8.8` with a 5/15
 * dash, centred on the range: the threshold was the invisible middle of an
 * 8.8 dp stripe that was mostly gaps, so a photo anywhere under it could be
 * in or out. It is not drawn any more (user, 2026-10-10: "the dashed band
 * really had no meaning that im aware of") — a divergence from the original,
 * whose dashed circle it was.
 */

/**
 * The circle, in dp: a solid line centred exactly on the range threshold.
 * Thin, so where it is can be read.
 */
const val RANGE_THRESHOLD_LINE_DP = 2f

/**
 * How far short of the threshold line's inner edge the arrow's tip stops,
 * in dp: enough to be seen as a gap, little enough to read as touching.
 */
const val ARROW_TIP_CLEARANCE_DP = 1.5f

/**
 * The bearing hold's stroke once it is served, in dp — the arc goes from a
 * thin charging line to a solid ring for as long as the finger is the
 * heading. It was 8.8, to cover the dashed band exactly; with the band gone
 * it only has to read as "taken", and grows outward from the threshold.
 */
const val BEARING_HOLD_ARMED_DP = 6f

/**
 * Where the bearing arrow's tip sits: just inside the threshold line.
 *
 * A divergence from the original, which puts the tip at `range × 1.3`, past
 * the circle — an arrow that ran out beyond the range said the range went
 * further than it does.
 */
fun arrowTipRadiusPx(thresholdPx: Float, density: Float): Float =
    thresholdPx - (RANGE_THRESHOLD_LINE_DP / 2f + ARROW_TIP_CLEARANCE_DP) * density

/**
 * The radius to draw the bearing hold's arc at, for a stroke of [strokeDp]:
 * just OUTSIDE the threshold, its inner edge on the line's outer edge. So
 * it widens outward when it arms, and never covers the threshold — or the
 * arrow's tip just inside it.
 */
fun bearingHoldRadiusPx(thresholdPx: Float, strokeDp: Float, density: Float): Float =
    thresholdPx + (RANGE_THRESHOLD_LINE_DP + strokeDp) / 2f * density
